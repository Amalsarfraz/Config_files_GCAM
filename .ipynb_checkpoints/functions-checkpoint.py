# Required imports - add these to the top of your functions.py file
import os
import copy
import time
import logging
import itertools
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple, Optional, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logger
logger = logging.getLogger(__name__)



@dataclass
class ScenarioParameters:
    """Parameter configuration for scenario generation."""
    ssps: List[str] = field(default_factory=lambda: ["SSP1", "SSP2", "SSP3", "SSP4", "SSP5"])
    rcps: List[str] = field(default_factory=lambda: ["2p6", "4p5", "6p0", "8p5"])
    pr_adoption_rates: List[int] = field(default_factory=lambda: [0, 25, 50, 75, 100])
    technology_levels: List[str] = field(default_factory=lambda: ["Basic", "Advanced"])
    supply_capacities: List[str] = field(default_factory=lambda: ["Low", "Medium", "High"])
    allocation_regulations: List[str] = field(default_factory=lambda: ["Market-driven", "Regulatory"])

    def total_scenarios(self) -> int:
        """Calculate total number of scenario combinations."""
        return (len(self.ssps) * len(self.rcps) * len(self.pr_adoption_rates) * 
                len(self.technology_levels) * len(self.supply_capacities) * 
                len(self.allocation_regulations))



# ──────────────────────────────────────────────────────────────────────────────
# SSP COMPONENT EXTRACTOR CLASS
# ──────────────────────────────────────────────────────────────────────────────

class SSPComponentExtractor:
    """Extract SSP-specific components from individual SSP XML files"""
    
    def __init__(self, ssp_files_directory: str = "./"):
        self.ssp_files_directory = ssp_files_directory
        self._component_cache = {}

    @lru_cache(maxsize=10)
    def extract_ssp_components(self, ssp: str) -> List[Tuple[str, str]]:
        """Extract components from specific SSP file using proper XML parsing."""
        ssp_file_path = os.path.join(self.ssp_files_directory, f"{ssp}_config.xml")
        
        if not os.path.exists(ssp_file_path):
            logger.error(f"SSP file not found: {ssp_file_path}")
            return []

        try:
            tree = ET.parse(ssp_file_path)
            root = tree.getroot()
            
            components = []
            
            # Extract all Value elements and their text content
            for value_elem in root.findall(".//Value"):
                name = value_elem.get("name")
                path = value_elem.text
                if name and path:
                    components.append((name, path.strip()))
            
            # Extract comments that are direct children of FileSet
            for elem in root:
                if hasattr(elem, 'tag') and elem.tag is ET.Comment:
                    comment_text = elem.text.strip()
                    components.append((f"COMMENT_{comment_text.lower().replace(' ', '_').replace('-', '_')}", f"<!-- {comment_text} -->"))
            
            logger.info(f"Extracted {len(components)} components from {ssp}")
            return components
            
        except ET.ParseError as e:
            logger.error(f"Failed to parse SSP file {ssp_file_path}: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to read SSP file {ssp_file_path}: {e}")
            return []

# ──────────────────────────────────────────────────────────────────────────────
# BASE TEMPLATE MANAGER CLASS
# ──────────────────────────────────────────────────────────────────────────────

class BaseTemplateManager:
    """Manage the base configuration template."""
    
    def __init__(self, template_path: str = "configuration_reuse100.xml"):
        self.template_path = template_path
        self.template_tree = self._load_template()
        self.template_root = self.template_tree.getroot()

    def _load_template(self) -> ET.ElementTree:
        """Load and validate base template."""
        if not os.path.exists(self.template_path):
            raise FileNotFoundError(f"Base template not found: {self.template_path}")
        
        try:
            tree = ET.parse(self.template_path)
            logger.info(f"Successfully loaded base template: {self.template_path}")
            return tree
        except ET.ParseError as e:
            raise ValueError(f"Invalid XML in template {self.template_path}: {e}")

    def _get_spa_code(self, ssp: str, rcp: str) -> str:
        """Get SPA code for SSP-RCP combination based on actual policy files"""
        # Fixed mapping based on actual policy files
        if rcp == "6p0":
            # RCP 6.0 has different SPA codes
            spa_mapping = {
                "SSP1": "1",
                "SSP2": "235",  # Uses spa235 for RCP 6.0
                "SSP3": "235",  # Uses spa235 for RCP 6.0
                "SSP4": "4", 
                "SSP5": "0"     # No spa5 file exists for RCP 6.0, fallback to spa0
            }
        else:
            # RCP 2.6 and 4.5 have standard mapping
            spa_mapping = {
                "SSP1": "1",
                "SSP2": "23", 
                "SSP3": "23",
                "SSP4": "4", 
                "SSP5": "5"
            }
        return spa_mapping.get(ssp, "0")

    def create_scenario_config(self, scenario_name: str, rcp: str, ssp: str) -> ET.Element:
        """Create deep copy of template for scenario with RCP and name updates."""
        scenario_root = copy.deepcopy(self.template_root)
        
        # Update scenario name
        self._update_scenario_name(scenario_root, scenario_name)
        
        # Update RCP policy target
        self._update_policy_target(scenario_root, rcp, ssp)
        
        # Update database location only
        self._update_database_location(scenario_root, scenario_name)
        
        return scenario_root

    def _update_scenario_name(self, root: ET.Element, scenario_name: str):
        """Update scenario name in Strings section."""
        strings_section = root.find("Strings")
        if strings_section is not None:
            for element in strings_section:
                if element.tag == "Value" and element.get("name") == "scenarioName":
                    element.text = scenario_name
                    logger.debug(f"Updated scenario name to: {scenario_name}")
                    break

    def _update_policy_target(self, root: ET.Element, rcp: str, ssp: str):
        """Update RCP policy target file reference."""
        files_section = root.find("Files")
        if files_section is not None:
            for element in files_section:
                if element.tag == "Value" and element.get("name") == "policy-target-file":
                    spa_code = self._get_spa_code(ssp, rcp)
                    policy_file = f"../input/policy/policy_target_{rcp}_spa{spa_code}.xml"
                    element.text = policy_file
                    logger.debug(f"Updated policy target to: {policy_file}")
                    break

    def _update_database_location(self, root: ET.Element, scenario_name: str):
        """Update database location for scenario isolation."""
        files_section = root.find("Files")
        if files_section is None:
            return

        for element in files_section:
            if element.tag == "Value" and element.get("name") == "xmldb-location":
                element.text = f"../output/db_{scenario_name}"
                logger.debug(f"Updated xmldb-location to: ../output/db_{scenario_name}")
                break

    def append_ssp_components(self, root: ET.Element, components: List[Tuple[str, str]]):
        """Append SSP-specific components to ScenarioComponents section."""
        scenario_section = root.find("ScenarioComponents")
        if scenario_section is None:
            logger.warning("ScenarioComponents section not found in template")
            return

        # Simply add every component from the SSP file
        for name, path in components:
            if name.startswith("COMMENT_") and path.startswith("<!--"):
                # Add XML comment
                comment_text = path.replace("<!--", "").replace("-->", "").strip()
                scenario_section.append(ET.Comment(f" {comment_text} "))
            else:
                # Add component
                ET.SubElement(scenario_section, "Value", name=name).text = path

        logger.info(f"Added {len(components)} SSP components")

# ──────────────────────────────────────────────────────────────────────────────
# MAIN CONFIGURATION GENERATOR CLASS
# ──────────────────────────────────────────────────────────────────────────────

class GCAMConfigurationGenerator:
    """Main configuration generator."""

    def __init__(self, parameters: ScenarioParameters, ssp_files_directory: str = "./"):
        self.parameters = parameters
        self.base_template = BaseTemplateManager()
        self.ssp_extractor = SSPComponentExtractor(ssp_files_directory)

    def generate_scenario_name(self, ssp: str, rcp: str, pr_rate: int, 
                             tech: str, supply: str, allocation: str) -> str:
        """Generate standardized scenario name."""
        tech_short = "Tech" if tech == "Advanced" else "Basic"
        supply_short = supply[0]  # L, M, H
        alloc_short = "Reg" if allocation == "Regulatory" else "Mkt"
        
        return f"{ssp}_{rcp}_{tech_short}_{supply_short}_{alloc_short}_PR{pr_rate}"

    def generate_all_configs(self, output_directory: str, 
                           ssp_filter: Optional[List[str]] = None,
                           use_concurrency: bool = True) -> List[str]:
        """Generate all scenario configurations."""
        
        # Create output directory
        output_path = Path(output_directory)
        output_path.mkdir(parents=True, exist_ok=True)

        # Generate scenario combinations
        scenario_combinations = list(self._generate_combinations(ssp_filter))
        
        logger.info(f"Generating {len(scenario_combinations)} scenario configurations...")

        if use_concurrency and len(scenario_combinations) > 1:
            generated_files = self._generate_concurrent(scenario_combinations, output_path)
        else:
            generated_files = self._generate_sequential(scenario_combinations, output_path)
        
        return generated_files

    def _generate_combinations(self, ssp_filter: Optional[List[str]] = None) -> Iterator[Tuple]:
        """Generate scenario parameter combinations."""
        filtered_ssps = self.parameters.ssps
        if ssp_filter:
            filtered_ssps = [ssp for ssp in self.parameters.ssps if ssp in ssp_filter]

        return itertools.product(
            filtered_ssps,
            self.parameters.rcps,
            self.parameters.pr_adoption_rates,
            self.parameters.technology_levels,
            self.parameters.supply_capacities,
            self.parameters.allocation_regulations
        )

    def _generate_sequential(self, scenarios: List[Tuple], output_path: Path) -> List[str]:
        """Generate configurations sequentially."""
        generated_files = []
        
        for i, scenario_params in enumerate(scenarios):
            try:
                file_path = self._generate_single_scenario(scenario_params, output_path)
                if file_path:
                    generated_files.append(file_path)
                    logger.info(f"Generated ({i+1}/{len(scenarios)}): {Path(file_path).name}")
            except Exception as e:
                logger.error(f"Failed to generate scenario {scenario_params}: {e}")

        return generated_files

    def _generate_concurrent(self, scenarios: List[Tuple], output_path: Path) -> List[str]:
        """Generate configurations using thread pool."""
        generated_files = []
        max_workers = min(8, len(scenarios))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_scenario = {
                executor.submit(self._generate_single_scenario, scenario_params, output_path): scenario_params
                for scenario_params in scenarios
            }
            
            completed = 0
            for future in as_completed(future_to_scenario):
                scenario_params = future_to_scenario[future]
                try:
                    file_path = future.result()
                    if file_path:
                        generated_files.append(file_path)
                        completed += 1
                        logger.info(f"Generated ({completed}/{len(scenarios)}): {Path(file_path).name}")
                except Exception as e:
                    logger.error(f"Failed to generate scenario {scenario_params}: {e}")

        return generated_files

    def _generate_single_scenario(self, scenario_params: Tuple, output_path: Path) -> Optional[str]:
        """Generate a single scenario configuration file."""
        ssp, rcp, pr_rate, tech, supply, allocation = scenario_params
        
        # Generate scenario name
        scenario_name = self.generate_scenario_name(ssp, rcp, pr_rate, tech, supply, allocation)

        try:
            # 1. Create base configuration from template
            config_root = self.base_template.create_scenario_config(scenario_name, rcp, ssp)

            # 2. Get SSP-specific components
            ssp_components = self.ssp_extractor.extract_ssp_components(ssp)
            
            if not ssp_components:
                logger.error(f"No components extracted for {ssp}")
                return None
            
            # 3. Use SSP components exactly as they are (no substitutions)
            components_to_add = []
            for name, path in ssp_components:
                components_to_add.append((name, path))

            # 4. Append all components to configuration
            self.base_template.append_ssp_components(config_root, components_to_add)

            # 5. Write configuration file without prettification
            output_file = output_path / f"{scenario_name}.xml"
            xml_string = ET.tostring(config_root, encoding="unicode")

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(xml_string)

            return str(output_file)

        except Exception as e:
            logger.error(f"Error generating scenario {scenario_name}: {e}")
            return None


# ──────────────────────────────────────────────────────────────────────────────
# RUNNINg entire ensemble
# ──────────────────────────────────────────────────────────────────────────────


def run_full_generation():
    """Run full configuration generation."""
    
    # Configuration parameters - MODIFY HERE for different runs
    scenario_params = ScenarioParameters(
        ssps=["SSP1", "SSP2", "SSP3", "SSP4", "SSP5"],      # All SSPs
        rcps=["2p6", "4p5", "6p0", "8p5"],                  # All RCPs  
        pr_adoption_rates=[0, 25, 50, 75, 100],             # All PR rates
        technology_levels=["Basic", "Advanced"],             # All tech levels
        supply_capacities=["Low", "Medium", "High"],         # All supply levels
        allocation_regulations=["Market-driven", "Regulatory"] # All allocation types
    )

    try:
        # Initialize generator
        config_generator = GCAMConfigurationGenerator(
            parameters=scenario_params,
            ssp_files_directory="./"  # Change this to the directory containing your SSP_config.xml files
        )

        logger.info(f"Generating {scenario_params.total_scenarios()} total scenario configurations...")

        # Generate configurations
        start_time = time.time()

        generated_files = config_generator.generate_all_configs(
            output_directory="configs_ensemble_complete",
            ssp_filter=None,  # Set to specific SSPs to filter, or None for all
            use_concurrency=True  # Set to False for sequential processing
        )

        end_time = time.time()
        generation_time = end_time - start_time

        # Performance summary
        logger.info(f"Successfully generated {len(generated_files)} configuration files")
        logger.info(f"Generation completed in {generation_time:.2f} seconds")
        if generated_files:
            logger.info(f"Average: {generation_time/len(generated_files):.3f} seconds per file")

        # Display sample of generated files
        print(f"\n✓ Generated {len(generated_files)} configuration files in {generation_time:.2f}s")
        print("\nSample generated files:")
        for i, file_path in enumerate(generated_files[:10]):
            print(f"  {i+1:2d}. {Path(file_path).name}")
        
        if len(generated_files) > 10:
            print(f"  ... and {len(generated_files) - 10} more files")

        return generated_files

    except Exception as e:
        logger.error(f"Configuration generation failed: {e}")
        raise


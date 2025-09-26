# GCAM Configuration Generator

This project generates GCAM (Global Change Analysis Model) scenario configuration files by combining base templates with SSP-specific components across multiple parameter combinations.

## Files Overview

### Core Files
- `functions.py` - Contains all the classes and functions for generating GCAM configurations
- `20250927 Config files generation.ipynb` - Jupyter notebook interface for running the generator
- `configuration_reuse100.xml` - Base template configuration file
- `SSP1_config.xml` to `SSP5_config.xml` - SSP-specific component files

### Configuration Files

#### Base Template
- `configuration_reuse100.xml` - Core GCAM configuration template that serves as the foundation for all generated scenarios. Contains default settings for all GCAM components including energy systems, land use, water, emissions, and solver configurations.

#### SSP Component Files
The SSP (Shared Socioeconomic Pathways) files were extracted from `batch_GCAM_REF.xml`:

- `SSP1_config.xml` - Sustainability pathway components
- `SSP2_config.xml` - Middle of the road pathway components  
- `SSP3_config.xml` - Regional rivalry pathway components
- `SSP4_config.xml` - Inequality pathway components
- `SSP5_config.xml` - Fossil-fueled development pathway components

### Naming Convention
Generated files follow the pattern: `{SSP}_{RCP}_{Tech}_{Supply}_{Allocation}_PR{Rate}.xml`

Examples:
- `SSP1_2p6_Basic_L_Mkt_PR0.xml`
- `SSP4_6p0_Tech_H_Reg_PR100.xml`

### Output Directories
- `config_sample_subset/` - Contains test subset configurations (typically 2-10 files for testing)
- `configs_ensemble_complete/` - Contains full ensemble configurations (all 2,400 possible combinations)
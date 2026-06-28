# Manual Metadata Candidates for Paper ID Repair

> Generated: 2026-06-28T18:39:32.200507
> Total: 16 papers need human metadata before repair

| # | paper_id | title | domains | has_md | suggestion |
|---|---|---|---|---|---|
| 1 | 4_an_improved_method_for_the_estimation_of_surface | [4]An improved method for the estimation of surface roughness of obsta | blowing_snow_physics | Y | Crossref title search needed |
| 2 | snowpack_2 | Snowpack_2 | blowing_snow_physics | Y | PRIORITY: identify real paper from paper.md first page |
| 3 | 3_note_on_aerodynamic_roughness_parameter_estimati | [3]Note on aerodynamic roughness-parameter estimation on the basis of  | blowing_snow_physics | Y | Crossref title search needed |
| 4 | 1_fifty_years_of_boundary_layer_theory_and_experim | [1]Fifty Years of Boundary-Layer Theory and Experiment. | blowing_snow_physics | Y | Crossref title search needed |
| 5 | 29_cfd_simulation_of_the_atmospheric_boundary_laye | [29]CFD simulation of the atmospheric boundary layer_ wall function pr | blowing_snow_physics | Y | Crossref title search needed |
| 6 | 53_large_eddy_simulations_of_flow_over_forested_ri | [53]Large-eddy simulations of flow over forested ridges | blowing_snow_physics | Y | Crossref title search needed |
| 7 | 32_an_analytical_wall_function_for_turbulent_flows | [32]An analytical wall-function__for turbulent flows and heat transfer | blowing_snow_physics | Y | Crossref title search needed |
| 8 | 7_测风塔风速的长程持续性特征研究_李庆雷 | [7]测风塔风速的长程持续性特征研究_李庆雷 | blowing_snow_physics | Y | Crossref title search needed |
| 9 | 33_a_model_of_atmospheric_boundary_layer_flow_abov | [33] A model of atmospheric boundary-layer flow above an isolated __tw | blowing_snow_physics | Y | Crossref title search needed |
| 10 | 37_flow_over_an_isolated_hill_of_moderate_slope | [37]Flow over an isolated hill of moderate slope | blowing_snow_physics | Y | Crossref title search needed |
| 11 | s11433_008_0106_6 | s11433-008-0106-6 | blowing_snow_physics | Y | PRIORITY: find DOI from original PDF or paper.md |
| 12 | 中国积雪的分布_李培基 | 中国积雪的分布_李培基 | blowing_snow_physics | Y | Manual DOI lookup or keep Chinese paper_id |
| 13 | 17_the_drag_on_an_undulating_surface_induced_by_th | [17]The drag on an undulating surface induced by the __flow of a turbu | blowing_snow_physics | Y | Crossref title search needed |
| 14 | 52_les_analysis_of_turbulent_boundary_layer_over_3 | [52]LES analysis of turbulent boundary layer over 3D steep hill covere | blowing_snow_physics | Y | Crossref title search needed |
| 15 | 40_on_the_parameterization_of_drag_over_small_scal | [40]On the parameterization of drag over small-scale topography in neu | blowing_snow_physics | Y | Crossref title search needed |
| 16 | snowpack_1 | Snowpack_1 | blowing_snow_physics | Y | PRIORITY: identify real paper from paper.md first page |

## Instructions
1. For each paper, find DOI via Crossref title search or PDF inspection
2. Add DOI to `data/repair/manual_metadata_candidates.json`
3. Run `python scripts/enrich_library_metadata.py --apply` after adding DOIs
4. Then `python scripts/repair_paper_ids.py --export-mapping repair_final.json`
5. Review `repair_final.json`, set `apply=true` for confirmed entries
6. Finally: `python scripts/repair_paper_ids.py --mapping repair_final.json --apply --backup`

## Priority Queue
1. snowpack_1, snowpack_2 - temporary filenames from batch import
2. s11433_008_0106_6 - journal article ID, find DOI
3. 11 [N]_title_slug papers - need DOI from Crossref title search
4. Chinese entries - keep Chinese paper_id if no DOI
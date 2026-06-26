"""现有 15 篇 raw PDF → paper_id 映射

paper_id 命名规则：年份_首位作者_中文标题（snake_case，作文件夹名与 paper.md 标识）。
权威的年份/作者/标题等书目信息由 literature_catalog.json 记录，paper_id 仅为稳定标识。

其中两组为重复上传（md 字节完全相同），仅保留一条，重复 raw 列于 DUPLICATE_RAW_STEMS：
  - 1999悬移控制方程 ≡ Dery_Yau_1999_A_Bulk_Blowing_Snow_Model  (Déry & Yau 1999, A Bulk Blowing Snow Model)
  - Comola_et_al_2017_Fragmentation_of_wind_blown_snow_crystals ≡ comola2017破碎  (Comola et al. 2017)
"""

# raw 文件名(去后缀) → paper_id
RAW_STEM_TO_PAPER_ID = {
    "1982野外升华率实验": "1982_schmidt_风吹雪垂直剖面",
    "1988雪升华率": "1988_dery_吹雪升华热力学",
    "1999shaoli起动": "1999_shao_风沙跃移数值模拟",
    "1999悬移控制方程": "1999_dery_吹雪体相模型",
    "Comola_et_al_2017_Fragmentation_of_wind_blown_snow_crystals": "2017_comola_风吹雪晶体破碎",
    "Gordon粒径分布": "2010_gordon_吹雪粒径分布",
    "Nishimura粒径分布": "2000_nishimura_南极吹雪观测",
    "Sugiura–Maeno击溅": "2000_sugiura_吹雪击溅函数",
    "Wang_2023_drag_model_finite_sized_particle_JFM": "2023_wang_有限粒径颗粒阻力模型",
    "cryowrf-egusphere-2026-2132": "2026_viaro_高山吹雪云过程",
    "huang2025破碎": "2025_huang_雪粒破碎促进升华",
    "jfm.2021.329": "2021_zheng_跃移床面湍流调制",
    "s11433-008-0106-6": "2008_wang_风沙跃移与悬移运动",
}

# 重复上传的 raw stem（不单独建 paper，仅记录）
DUPLICATE_RAW_STEMS = {
    "Dery_Yau_1999_A_Bulk_Blowing_Snow_Model",   # 同 1999悬移控制方程
    "comola2017破碎",                              # 同 Comola_et_al_2017_...
}

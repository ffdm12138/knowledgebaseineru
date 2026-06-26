"""src/writer — 综述写作 skill 的核心模块

流程：job_manager → topic_parser → catalog_matcher → deep_reader
     → story_builder → tex_project + figure_manager + bib_manager

所有 LLM 步骤只生成 prompt 文本，不内置 LLM client。
"""

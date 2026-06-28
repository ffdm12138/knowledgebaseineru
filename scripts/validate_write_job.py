"""CLI wrapper for writing job validation."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.writer.job_validator import validate_job


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    result = validate_job(args.job)
    if result["valid"]:
        logger.info(f"✅ 写作任务 {args.job} 校验通过（可移植: {result['portable']}）")
        for warning in result["warnings"]:
            logger.warning(f"  ⚠ {warning}")
        return 0
    logger.error(f"❌ {args.job} 发现 {len(result['errors'])} 个 fatal 问题：")
    for error in result["errors"]:
        logger.error(f"  - {error}")
    for warning in result["warnings"]:
        logger.warning(f"  ⚠ {warning}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

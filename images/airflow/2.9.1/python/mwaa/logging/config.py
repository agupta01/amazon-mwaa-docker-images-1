# Python imports
import logging
import os

# 3rd party imports
from airflow.config_templates.airflow_local_settings import (
    BASE_LOG_FOLDER,
    DAG_PROCESSOR_MANAGER_LOG_LOCATION,
    DEFAULT_LOGGING_CONFIG,
    PROCESSOR_FILENAME_TEMPLATE,
)

# Our imports
from mwaa.logging import cloudwatch_handlers

# We adopt the default logging configuration from Airflow and do the necessary changes
# to setup logging with CloudWatch Logs.
LOGGING_CONFIG = {
    **DEFAULT_LOGGING_CONFIG,
}


def _qualified_name(cls: type) -> str:
    module = cls.__module__
    qualname = cls.__qualname__
    return f"{module}.{qualname}"


def _get_mwaa_logging_env_vars(source: str):
    log_group_arn = os.environ.get(
        f"MWAA__LOGGING__AIRFLOW_{source.upper()}_LOG_GROUP_ARN", None
    )
    log_level = os.environ.get(
        f"MWAA__LOGGING__AIRFLOW_{source.upper()}_LOG_LEVEL",
        logging.getLevelName(logging.INFO),
    )
    logging_enabled = os.environ.get(
        f"MWAA__LOGGING__AIRFLOW_{source.upper()}_LOGS_ENABLED", "false"
    )

    return (
        log_group_arn,
        log_level,
        logging_enabled.lower() == "true",
    )


def _configure_task_logging():
    log_group_arn, log_level, logging_enabled = _get_mwaa_logging_env_vars("task")
    if log_group_arn is not None:
        # Setup CloudWatch logging.
        LOGGING_CONFIG["handlers"]["task"] = {
            "class": _qualified_name(cloudwatch_handlers.TaskLogHandler),
            "formatter": "airflow",
            "filters": ["mask_secrets"],
            "base_log_folder": str(os.path.expanduser(BASE_LOG_FOLDER)),
            "log_group_arn": log_group_arn,
            "enabled": logging_enabled,
        }
        LOGGING_CONFIG["loggers"]["airflow.task"].update(
            {
                "level": log_level,
            }
        )


def _configure_dag_processing_logging():
    log_group_arn, log_level, logging_enabled = _get_mwaa_logging_env_vars(
        "dag_processing"
    )
    if log_group_arn is not None:
        # Setup CloudWatch logging for DAG Processor Manager.
        LOGGING_CONFIG["handlers"]["processor_manager"] = {
            "class": _qualified_name(cloudwatch_handlers.DagProcessorManagerLogHandler),
            "formatter": "airflow",
            "log_group_arn": log_group_arn,
            "stream_name": os.path.basename(DAG_PROCESSOR_MANAGER_LOG_LOCATION),
            "enabled": logging_enabled,
        }
        LOGGING_CONFIG["loggers"]["airflow.processor_manager"] = {
            "handlers": ["processor_manager"],
            "level": log_level,
            "propagate": False,
        }

        # Setup CloudWatch logging for DAG processing.
        LOGGING_CONFIG["handlers"]["processor"] = {
            "class": _qualified_name(cloudwatch_handlers.DagProcessingLogHandler),
            "formatter": "airflow",
            "log_group_arn": log_group_arn,
            "stream_name_template": PROCESSOR_FILENAME_TEMPLATE,
            "enabled": logging_enabled,
        }
        LOGGING_CONFIG["loggers"]["airflow.processor"] = {
            "handlers": ["processor"],
            "level": log_level,
            "propagate": False,
        }


def _configure_subprocesses_logging(
    subprocess_name: str,
    log_group_arn: str | None,
    log_level: str,
    logging_enabled: bool,
):
    handler_name = f"mwaa_{subprocess_name}"
    logger_name = f"mwaa.{subprocess_name}"
    if log_group_arn is not None:
        LOGGING_CONFIG["handlers"][handler_name] = {
            "class": _qualified_name(cloudwatch_handlers.SubprocessLogHandler),
            "formatter": "airflow",
            "filters": ["mask_secrets"],
            "log_group_arn": log_group_arn,
            "stream_name_prefix": subprocess_name,
            "subprocess_name": subprocess_name,
            "enabled": logging_enabled,
        }
        # Setup CloudWatch logging.
        LOGGING_CONFIG["loggers"][logger_name] = {
            "handlers": [handler_name],
            "level": log_level,
            "propagate": False,
        }


def _configure():
    _configure_task_logging()
    _configure_dag_processing_logging()
    for comp in ["worker", "scheduler", "webserver"]:
        args = _get_mwaa_logging_env_vars(comp)
        _configure_subprocesses_logging(comp, *args)
        _configure_subprocesses_logging(f"{comp}_requirements", *args)


_configure()

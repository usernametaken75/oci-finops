"""Environment-based configuration for the ETL pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class OciConfig:
    tenancy_ocid: str = field(default_factory=lambda: os.environ["OCI_TENANCY_OCID"])
    region: str = field(default_factory=lambda: os.environ.get("OCI_REGION", "us-ashburn-1"))
    config_file: str = field(default_factory=lambda: os.environ.get("OCI_CONFIG_FILE", "~/.oci/config"))
    config_profile: str = field(default_factory=lambda: os.environ.get("OCI_CONFIG_PROFILE", "DEFAULT"))
    namespace: str = "bling"

    @property
    def bucket_name(self) -> str:
        return self.tenancy_ocid


@dataclass(frozen=True)
class PgConfig:
    host: str = field(default_factory=lambda: os.environ.get("PG_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.environ.get("PG_PORT", "5432")))
    database: str = field(default_factory=lambda: os.environ.get("PG_DATABASE", "oci_finops"))
    user: str = field(default_factory=lambda: os.environ.get("PG_USER", "finops"))
    password: str = field(default_factory=lambda: os.environ.get("PG_PASSWORD", "changeme"))

    @property
    def dsn(self) -> str:
        return f"host={self.host} port={self.port} dbname={self.database} user={self.user} password={self.password}"


@dataclass(frozen=True)
class EtlConfig:
    batch_size: int = field(default_factory=lambda: int(os.environ.get("ETL_BATCH_SIZE", "10000")))
    temp_dir: Path = field(default_factory=lambda: Path(os.environ.get("ETL_TEMP_DIR", "/tmp/oci-finops")))
    focus_report_year: str | None = field(default_factory=lambda: os.environ.get("FOCUS_REPORT_YEAR"))

    def __post_init__(self):
        self.temp_dir.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class NotificationConfig:
    ons_topic_ocid: str | None = field(default_factory=lambda: os.environ.get("ONS_TOPIC_OCID") or None)
    smtp_host: str | None = field(default_factory=lambda: os.environ.get("SMTP_HOST") or None)
    smtp_port: int = field(default_factory=lambda: int(os.environ.get("SMTP_PORT", "587")))
    smtp_user: str | None = field(default_factory=lambda: os.environ.get("SMTP_USER") or None)
    smtp_password: str | None = field(default_factory=lambda: os.environ.get("SMTP_PASSWORD") or None)
    smtp_from: str = field(default_factory=lambda: os.environ.get("SMTP_FROM", "finops-alerts@example.com"))
    smtp_to: str = field(default_factory=lambda: os.environ.get("SMTP_TO", ""))


@dataclass(frozen=True)
class AppConfig:
    oci: OciConfig = field(default_factory=OciConfig)
    pg: PgConfig = field(default_factory=PgConfig)
    etl: EtlConfig = field(default_factory=EtlConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)


def load_config() -> AppConfig:
    return AppConfig()

"""Configuration management for MeshCore TCP Proxy."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("meshcore.proxy.config")


@dataclass
class ProxyConfig:
    """Proxy configuration.

    Attributes:
        listen_host: TCP server listen address (0.0.0.0 = all interfaces)
        listen_port: TCP server listen port
        max_clients: Maximum concurrent clients (0 = unlimited)
        backend_type: Backend type ('serial' or 'ble')
        serial_port: Serial port path (for serial backend)
        serial_baudrate: Serial baudrate (for serial backend)
        ble_address: BLE device address (for BLE backend)
        auto_reconnect: Auto-reconnect on disconnect
        reconnect_delay: Delay between reconnect attempts (seconds)
        max_reconnect_attempts: Max reconnect attempts (0 = infinite)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Log file path (None = stdout only)
        log_frames: Log frame data for debugging
    """

    # TCP Server
    listen_host: str = "0.0.0.0"
    listen_port: int = 5000
    max_clients: int = 5

    # Backend
    backend_type: str = "serial"  # 'serial' or 'ble'

    # Serial backend
    serial_port: Optional[str] = None
    serial_baudrate: int = 115200

    # BLE backend
    ble_address: Optional[str] = None

    # Reconnection
    auto_reconnect: bool = True
    reconnect_delay: int = 5
    max_reconnect_attempts: int = 0  # 0 = infinite

    # Logging
    log_level: str = "INFO"
    log_file: Optional[str] = None
    log_frames: bool = False

    @classmethod
    def from_yaml(cls, path: str) -> "ProxyConfig":
        """Load config from YAML file.

        Args:
            path: Path to YAML configuration file

        Returns:
            ProxyConfig instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If config file is invalid
        """
        config_path = Path(path)

        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        logger.debug(f"Loading configuration from {path}")

        with open(config_path, "r") as f:
            data = yaml.safe_load(f)

        if not data:
            logger.warning(f"Empty configuration file, using defaults")
            return cls()

        # Parse configuration sections
        proxy_config = data.get("proxy", {})
        backend_config = data.get("backend", {})
        logging_config = data.get("logging", {})

        return cls(
            # TCP Server
            listen_host=proxy_config.get("listen_host", "0.0.0.0"),
            listen_port=proxy_config.get("listen_port", 5000),
            max_clients=proxy_config.get("max_clients", 5),

            # Backend
            backend_type=backend_config.get("type", "serial"),
            serial_port=backend_config.get("serial_port"),
            serial_baudrate=backend_config.get("baudrate", 115200),
            ble_address=backend_config.get("ble_address"),
            auto_reconnect=backend_config.get("auto_reconnect", True),
            reconnect_delay=backend_config.get("reconnect_delay", 5),
            max_reconnect_attempts=backend_config.get("max_reconnect_attempts", 0),

            # Logging
            log_level=logging_config.get("level", "INFO"),
            log_file=logging_config.get("file"),
            log_frames=logging_config.get("log_frames", False),
        )

    def validate(self) -> None:
        """Validate configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        # Validate backend type
        if self.backend_type not in ("serial", "ble"):
            raise ValueError(
                f"Invalid backend_type '{self.backend_type}'. Must be 'serial' or 'ble'"
            )

        # Validate serial backend
        if self.backend_type == "serial":
            if not self.serial_port:
                raise ValueError("serial_port is required for serial backend")

            serial_path = Path(self.serial_port)
            if not serial_path.exists():
                logger.warning(
                    f"Serial port {self.serial_port} does not exist. "
                    "It may become available later."
                )

        # Validate BLE backend
        if self.backend_type == "ble":
            if not self.ble_address:
                raise ValueError("ble_address is required for BLE backend")

        # Validate port range
        if not (1 <= self.listen_port <= 65535):
            raise ValueError(
                f"Invalid listen_port {self.listen_port}. Must be 1-65535"
            )

        # Validate log level
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level.upper() not in valid_levels:
            raise ValueError(
                f"Invalid log_level '{self.log_level}'. "
                f"Must be one of: {', '.join(valid_levels)}"
            )

        logger.info("Configuration validated successfully")

    def __str__(self) -> str:
        """String representation of configuration."""
        return (
            f"ProxyConfig(\n"
            f"  TCP Server: {self.listen_host}:{self.listen_port}\n"
            f"  Backend: {self.backend_type}\n"
            f"  Serial: {self.serial_port} @ {self.serial_baudrate} baud\n"
            f"  BLE: {self.ble_address}\n"
            f"  Log Level: {self.log_level}\n"
            f")"
        )

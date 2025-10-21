"""CLI entry point for MeshCore TCP Proxy."""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from .proxy import MeshCoreTCPProxy
from .config import ProxyConfig

logger = logging.getLogger("meshcore.proxy")


def setup_logging(level: str, log_file: str = None):
    """Setup logging configuration.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path
    """
    handlers = [logging.StreamHandler(sys.stdout)]

    if log_file:
        log_path = Path(log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path))

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )


def main():
    """Main entry point for meshcore-tcp-proxy command."""
    parser = argparse.ArgumentParser(
        description="MeshCore TCP Proxy - Expose Serial/BLE devices over TCP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start with serial device
  meshcore-tcp-proxy --serial /dev/ttyUSB0

  # Start with config file
  meshcore-tcp-proxy --config /etc/meshcore-proxy/config.yaml

  # Start on custom port
  meshcore-tcp-proxy --serial /dev/ttyUSB0 --port 6000

  # Debug mode with frame logging
  meshcore-tcp-proxy --serial /dev/ttyUSB0 --debug --log-frames
        """
    )

    parser.add_argument(
        '--config', '-c',
        help='Path to configuration file (YAML)'
    )
    parser.add_argument(
        '--serial', '-s',
        help='Serial port (e.g., /dev/ttyUSB0) - overrides config file'
    )
    parser.add_argument(
        '--baudrate', '-b',
        type=int,
        default=115200,
        help='Serial baudrate (default: 115200)'
    )
    parser.add_argument(
        '--ble',
        help='BLE device address (e.g., C2:2B:A1:D5:3E:B6) - overrides config file'
    )
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='TCP listen host (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=5000,
        help='TCP listen port (default: 5000)'
    )
    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--log-file',
        help='Log file path (default: stdout only)'
    )
    parser.add_argument(
        '--log-frames',
        action='store_true',
        help='Log frame data (verbose, for debugging)'
    )

    args = parser.parse_args()

    # Load configuration
    if args.config:
        try:
            config = ProxyConfig.from_yaml(args.config)
            logger.info(f"Loaded configuration from {args.config}")
        except FileNotFoundError:
            print(f"Error: Configuration file not found: {args.config}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error loading configuration: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Use defaults
        config = ProxyConfig()

    # Override with CLI arguments
    if args.serial:
        config.backend_type = 'serial'
        config.serial_port = args.serial
        config.serial_baudrate = args.baudrate

    if args.ble:
        config.backend_type = 'ble'
        config.ble_address = args.ble

    config.listen_host = args.host
    config.listen_port = args.port

    if args.debug:
        config.log_level = 'DEBUG'

    if args.log_file:
        config.log_file = args.log_file

    if args.log_frames:
        config.log_frames = True

    # Setup logging
    setup_logging(config.log_level, config.log_file)

    # Validate configuration
    try:
        config.validate()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    # Create proxy
    proxy = MeshCoreTCPProxy(config)

    # Setup signal handlers for graceful shutdown
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def signal_handler(sig):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(proxy.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

    # Run proxy
    try:
        loop.run_until_complete(proxy.start())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        loop.close()


if __name__ == '__main__':
    main()

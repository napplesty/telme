"""Client entry point."""
import click

from client.tui.app import TelmeApp
from client.crypto.key_manager import KeyManager
from client.utils.logger import get_logger

logger = get_logger(__name__)


@click.command()
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.option("--show-key", is_flag=True, help="Print your public key and exit")
def main(debug: bool, show_key: bool):
    """Run the Telme chat client."""
    if show_key:
        km = KeyManager()
        km.get_or_create_keys()
        click.echo(f"User ID:    {km.user_id}")
        click.echo(f"Public Key: {km.public_key_base64}")
        return

    if debug:
        logger.info("Running in debug mode")

    # Run the TUI application
    app = TelmeApp()
    app.run()


if __name__ == "__main__":
    main()

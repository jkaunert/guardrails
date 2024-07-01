import time
from typing import Optional

import typer
from rich.console import Console

from guardrails.cli.guardrails import guardrails as gr_cli
from guardrails.cli.hub.install import (  # JC: I don't like this import. Move fns?
    install_hub_module,
    add_to_hub_inits,
    run_post_install,
)
from guardrails.cli.hub.utils import get_site_packages_location
from guardrails.cli.server.hub_client import get_validator_manifest


console = Console()


@gr_cli.command(name="create")
def create_command(
    validators: str = typer.Option(
        help="A comma-separated list of validator hub URIs. ",
    ),
    name: Optional[str] = typer.Option(
        default=None, help="The name of the guard to define in the file."
    ),
    filepath: str = typer.Option(
        default="config.py",
        help="The path to which the configuration file should be saved.",
    ),
    dry_run: bool = typer.Option(
        default=False,
        is_flag=True,
        help="Print out the validators to be installed without making any changes.",
    ),
):
    installed_validators = split_and_install_validators(validators, dry_run)
    new_config_file = generate_config_file(installed_validators, name)
    if dry_run:
        console.print(f"Not actually saving output to {filepath}")
        console.print(f"The following would have been written:\n{new_config_file}")
    else:
        with open(filepath, "wt") as fout:
            fout.write(new_config_file)
        console.print(f"Saved configuration to {filepath}")


def split_and_install_validators(validators: str, dry_run: bool = False):
    """Given a comma-separated list of validators, check the hub to make sure all of
    them exist, install them, and return a list of 'imports'."""
    # Quick sanity check after split:
    validators = validators.split(",")
    stripped_validators = list()
    manifests = list()
    site_packages = get_site_packages_location()

    # hub://blah -> blah, then download the manifest.
    with console.status("Checking validator manifests") as status:
        for v in validators:
            status.update(f"Prefetching {v}")
            if not v.strip().startswith("hub://"):
                console.print(
                    f"WARNING: Validator {v} does not appear to be a valid URI."
                )
                return
            stripped_validator = v.lstrip("hub://")
            stripped_validators.append(stripped_validator)
            manifests.append(get_validator_manifest(stripped_validator))

    # We should make sure they exist.
    with console.status("Installing validators") as status:
        for manifest, validator in zip(manifests, stripped_validators):
            status.update(f"Installing {validator}")
            if not dry_run:
                install_hub_module(manifest, site_packages, quiet=True)
                run_post_install(manifest, site_packages)
                add_to_hub_inits(manifest, site_packages)
            else:
                console.print(f"Fake installing {validator}")
                time.sleep(1)

    # Pull the hub information from each of the installed validators and return it.
    return [manifest.exports[0] for manifest in manifests]


def generate_config_file(validators: str, name: Optional[str] = None) -> str:
    config_lines = [
        "from guardrails import Guard",
    ]

    # Import one or more validators.
    if len(validators) == 1:
        config_lines.append(f"from guardrails.hub import {validators[0]}")
    else:
        multiline_import = ",\n\t".join(validators)
        config_lines.append(f"from guardrails.hub import (\n\t{multiline_import}\n)")

    # Initialize our guard.
    config_lines.append("guard = Guard()")
    if name is not None:
        config_lines.append(f"guard.name = {name.__repr__()}")

    # Append validators:
    if len(validators) == 1:
        config_lines.append(f"guard.use({validators[0]}())")
    else:
        multi_use = ",\n".join(["\t" + validator + "()" for validator in validators])
        config_lines.append(f"guard.use_many(\n{multi_use}\n)")

    return "\n".join(config_lines)

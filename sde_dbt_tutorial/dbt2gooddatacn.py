#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (C) 2021 GoodData Corporation
import argparse
import os
from gooddata.metadata import Metadata
from gooddata.config import Config


def parse_arguments():
    # noinspection PyTypeChecker
    parser = argparse.ArgumentParser(
        conflict_handler="resolve",
        description="Update GoodData.CN data sources and workspaces based on dbt project",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    group_data_source = parser.add_mutually_exclusive_group()
    group_data_source.add_argument(
        '-t', '--targets', nargs='*', default=(),
        help=f'Space separated list of targets(data sources) to be processed.')
    group_data_source.add_argument(
        '-at', '--all-targets', action='store_true', default=False, help="Process all targets (data sources)"
    )
    parser.add_argument(
        '-dg',
        '--deploy-gooddata-from-files',
        action='store_true',
        default=False,
        help="Deploy from stored GoodData declarative definitions (YML) only"
    )
    return parser.parse_args()


def process_data_source(metadata, config, dbt_data_source, dbt_output, deploy_gooddata_from_files):
    gd_type = config.get_gd_data_source_type(dbt_data_source['type'])
    # Create or update the data source in GD.CN
    metadata.register_data_source(config, dbt_output, gd_type, dbt_data_source)
    if deploy_gooddata_from_files:
        pdm = metadata.read_declarative_yaml(dbt_output, 'pdm')
        # TODO - convert to DeclarativePdm
    else:
        scan_result = metadata.scan_pdm(dbt_output)
        # Filter scan_result by all required tables + convert it into Declarative PDM
        pdm = metadata.scan_result_to_pdm(scan_result, config.all_tables)
        # Dump data source declarative definition to local file
        metadata.write_declarative_yaml(pdm.to_dict(), dbt_output, 'pdm')

    # Store PDM into GD.CN
    metadata.store_pdm(dbt_output, pdm)


def process_workspace(metadata, workspace, dbt_output, ldm, deploy_gooddata_from_files):
    workspace_id = workspace['id'] + '_' + dbt_output
    print(f'Processing workspace {workspace_id}')
    workspace_name = workspace['name'] + ' (' + dbt_output + ')'
    # Create or update the workspace in GD.CN
    metadata.create_or_update_workspace(workspace_id, workspace_name)
    if deploy_gooddata_from_files:
        ldm = metadata.read_declarative_yaml(workspace_id, 'ldm')
        # TODO - convert to DeclarativeLdm
    else:
        # Include only relevant LDM datasets into the workspace
        metadata.filter_ldm_by_workspace_tables(ldm, workspace['tables'])
        # Dump workspace declarative definition to local file
        metadata.write_declarative_yaml(ldm.to_dict(), workspace_id, 'ldm')

    # Deploy LDM into GD.CN
    metadata.store_ldm(workspace_id, ldm)


################################################
# Manage data sources and workspaces
################################################

def main():
    args = parse_arguments()
    config = Config()

    api_token = os.getenv('TIGER_API_TOKEN')
    if not api_token:
        raise Exception('No API token set in TIGER_API_TOKEN ENV variable!')
    metadata = Metadata(
        os.getenv('TIGER_ENDPOINT', 'http://localhost:3000'),
        os.getenv('TIGER_API_TOKEN')
    )

    selected_dbt_outputs = {}
    for dbt_output, dbt_data_source in config.dbt_outputs.items():
        if args.all_targets or dbt_output in args.targets:
            selected_dbt_outputs[dbt_output] = dbt_data_source

    for dbt_output, dbt_data_source in selected_dbt_outputs.items():
        print(f'Processing dbt target {dbt_output}')
        process_data_source(metadata, config, dbt_data_source, dbt_output, args.deploy_gooddata_from_files)

        # Generate complete LDM from PDM and distribute datasets into workspaces based on the config of each workspace
        ldm = None
        # Generate LDM only if deploy_gooddata_from_files is not requested
        if not args.deploy_gooddata_from_files:
            ldm = metadata.generate_ldm(dbt_output)
        for workspace in config.gd_workspaces:
            process_workspace(metadata, workspace, dbt_output, ldm, args.deploy_gooddata_from_files)


# TODO
# 1. Support all database engines
# 2. Deploy PDM/LDM only (from yamls)
# 3. Move metadata funcs into python-sdk
# 4. Generate customer/state version id (recommended by Vasek Rek)
#    Do it in marts, not in core
#    Remove the option with tags, instead consider an option with schemas


if __name__ == "__main__":
    main()

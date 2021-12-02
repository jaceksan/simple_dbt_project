# -*- coding: utf-8 -*-
# (C) 2021 GoodData Corporation

import os
import re
from pathlib import Path
import yaml


class Config:
    def __init__(self):
        self.dbt_project = self.read_config_from_file('dbt_project.yml')
        self.gd_config = self.read_config_from_file('gooddata.yml')
        dbt_profile_dir = os.getenv('DBT_PROFILES_DIR', '~/.dbt')
        self.dbt_profiles = self.read_config_from_file(Path(dbt_profile_dir) / 'profiles.yml')
        self.project_profile_name = self.dbt_project['profile']
        self.dbt_outputs = self.dbt_profiles[self.project_profile_name]['outputs']
        self.gd_data_sources = self.gd_config.get('data_sources', {})
        self.gd_workspaces = self.gd_config.get('workspaces', {})
        self.override_data_source_props()

    @staticmethod
    def read_config_from_file(config_file):
        with open(config_file) as fp:
            return yaml.safe_load(fp)

    @staticmethod
    def get_gd_data_source_type(dbt_data_source_type):
        if dbt_data_source_type == 'postgres':
            return 'POSTGRESQL'
        elif dbt_data_source_type == 'snowflake':
            return 'SNOWFLAKE'
        elif dbt_data_source_type == 'redshift':
            return 'REDSHIFT'
        elif dbt_data_source_type == 'bigquery':
            return 'BIGQUERY'
        elif dbt_data_source_type == 'vertica':
            return 'VERTICA'
        else:
            raise Exception(f'Unsupported data source: {dbt_data_source_type}')

    @staticmethod
    def get_jdbc_vendor(dbt_data_source_type):
        if dbt_data_source_type == 'postgres':
            return 'postgresql'
        elif dbt_data_source_type == 'snowflake':
            return 'snowflake'
        elif dbt_data_source_type == 'redshift':
            return 'redshift'
        elif dbt_data_source_type == 'bigquery':
            return 'bigquery'
        elif dbt_data_source_type == 'vertica':
            return 'vertica'
        else:
            raise Exception(f'Unsupported data source: {dbt_data_source_type}')

    def override_data_source_props(self):
        # Adopt gooddata data source properties
        # When connection endpoints are different for dbt and for GD.CN (running in docker!)
        for data_source in self.gd_data_sources:
            for dbt_output, dbt_data_source in self.dbt_outputs.items():
                if data_source['dbt_output'] == dbt_output:
                    dbt_data_source['host'] = data_source['gooddata'].get('host', dbt_data_source['host'])
                    dbt_data_source['port'] = data_source['gooddata'].get('port', dbt_data_source['port'])

    @property
    def model_paths(self):
        model_paths = []
        for source_path in self.dbt_project['source-paths']:
            for dir_path, _, file_names in os.walk(source_path):
                model_paths.append({'dir_path': dir_path, 'file_names': file_names})
        return model_paths

    @staticmethod
    def parse_referenced_table(reference):
        return re.search(r"ref\('([^)]+)'\)", reference).group(1)

    def process_tests(self, tests, tables, table, column):
        for test in tests:
            if isinstance(test, dict):
                if 'relationships' in test:
                    tables[table['name']]['references'] = []
                    reference = {
                        'source_column': column['name'],
                        'referenced_table_id': self.parse_referenced_table(
                            test['relationships']['to']
                        ),
                        'referenced_table_column': test['relationships']['field']
                    }
                    tables[table['name']]['references'].append(reference)
            elif test == 'unique':
                tables[table['name']]['primary_key_column'] = column['name']

    def read_dbt_model(self, directory, file_name):
        file_path = os.path.join(directory['dir_path'], file_name)
        file_base, file_extension = os.path.splitext(file_name)
        if file_extension == '.yml':
            model = self.read_config_from_file(file_path)
            if 'models' in model:
                return model['models']
            else:
                return None

    def get_tables_from_dbt_model(self, directory):
        file_names = directory['file_names']
        tables = {}
        for file_name in file_names:
            file_base, file_extension = os.path.splitext(file_name)
            if file_extension == '.sql':
                tables[file_base] = {}
        for file_name in file_names:
            models = self.read_dbt_model(directory, file_name)
            if models:
                for table in models:
                    tables[table['name']] = {}
                    if 'columns' in table:
                        for column in table['columns']:
                            if 'tests' in column:
                                self.process_tests(column['tests'], tables, table, column)
        return tables

    def get_tables_from_dbt_model_tags(self, directory, tags):
        file_names = directory['file_names']
        tables = {}
        for file_name in file_names:
            models = self.read_dbt_model(directory, file_name)
            if models:
                for table in models:
                    if 'tags' in table:
                        for tag in tags:
                            if tag in table['tags']:
                                tables[table['name']] = {}
                    if table['name'] in tables and 'columns' in table:
                        for column in table['columns']:
                            if 'tests' in column:
                                self.process_tests(column['tests'], tables, table, column)
        return tables

    @property
    def all_tables(self):
        tables = {}
        model_paths = self.model_paths
        for workspace in self.gd_workspaces:
            workspace['tables'] = {}
            if 'dbt_models' in workspace:
                for model in workspace['dbt_models']:
                    for directory in model_paths:
                        if os.path.basename(directory['dir_path']) == model['name']:
                            workspace_tables = self.get_tables_from_dbt_model(directory)
                            tables.update(workspace_tables)
                            workspace['tables'].update(workspace_tables)
            elif 'tags' in workspace:
                for directory in model_paths:
                    workspace_tables = self.get_tables_from_dbt_model_tags(directory, workspace['tags'])
                    tables.update(workspace_tables)
                    workspace['tables'].update(workspace_tables)
        return tables

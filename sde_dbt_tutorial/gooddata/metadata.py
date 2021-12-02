# -*- coding: utf-8 -*-
# (C) 2021 GoodData Corporation
import re

import yaml
from gooddata_metadata_client.api import organization_model_controller_api
from gooddata_metadata_client.api import data_source_layout_controller_api
from gooddata_metadata_client.api import declarative_layout_controller_api
from gooddata_metadata_client.api import workspace_object_controller_api
from gooddata_metadata_client.api import data_source_actions_controller_api
from gooddata_metadata_client.model.declarative_column import DeclarativeColumn
from gooddata_metadata_client.model.declarative_ldm import DeclarativeLdm
from gooddata_metadata_client.model.declarative_pdm import DeclarativePdm
from gooddata_metadata_client.model.declarative_table import DeclarativeTable
from gooddata_metadata_client.model.declarative_tables import DeclarativeTables
from gooddata_metadata_client.model.json_api_data_source_in import JsonApiDataSourceIn
from gooddata_metadata_client.model.json_api_data_source_in_attributes import JsonApiDataSourceInAttributes
from gooddata_metadata_client.model.json_api_data_source_in_document import JsonApiDataSourceInDocument
from gooddata_metadata_client.model.json_api_workspace_in import JsonApiWorkspaceIn
from gooddata_metadata_client.model.json_api_workspace_in_document import JsonApiWorkspaceInDocument
from gooddata_metadata_client.model.json_api_workspace_out_attributes import JsonApiWorkspaceOutAttributes
from gooddata_metadata_client.exceptions import NotFoundException
from gooddata_scan_client.api import actions_api as scan_actions_api
from gooddata_scan_client.model.scan_result_pdm import ScanResultPdm
from gooddata_sdk import GoodDataApiClient


class Metadata:
    def __init__(self, host, api_key):
        client = GoodDataApiClient(host=host, token=api_key)
        md_client = client.metadata_client
        scan_client = client.scan_client
        self.org_model = organization_model_controller_api.OrganizationModelControllerApi(md_client)
        self.workspace_model = workspace_object_controller_api.WorkspaceObjectControllerApi(md_client)
        self.data_source_model = data_source_actions_controller_api.DataSourceActionsControllerApi(md_client)
        self.scan_model = scan_actions_api.ActionsApi(scan_client)
        self.ds_layout = data_source_layout_controller_api.DataSourceLayoutControllerApi(md_client)
        self.ws_layout = declarative_layout_controller_api.DeclarativeLayoutControllerApi(md_client)
        self.workspace_id = None

    def get_workspace_ids(self):
        result = self.org_model.get_all_entities_workspaces(_check_return_type=False, size=100)
        return [w['id'] for w in result.data]

    def list_workspaces(self):
        result = self.org_model.get_all_entities_workspaces(include=['workspaces'], _check_return_type=False, size=100)
        data = [
            [element['attributes']['name'], element['id']]
            for element in result.data
        ]
        return {
            'headers': ['Name', 'Id'],
            'data': data
        }

    def list_data_sources(self):
        return self.org_model.get_all_entities_data_sources(_check_return_type=False, size=100).data

    @staticmethod
    def _get_entities_basic(result, entity_prefix=''):
        data = [
            [element['attributes']['title'], entity_prefix + element['id']]
            for element in result.data
        ]
        return {
            'headers': ['Title', 'Id'],
            'data': data
        }

    def list_labels(self):
        result = self.workspace_model.get_all_entities_labels(self.workspace_id, _check_return_type=False, size=100)
        return self._get_entities_basic(result, 'label/')

    def list_metrics(self):
        result = self.workspace_model.get_all_entities_metrics(self.workspace_id, _check_return_type=False, size=100)
        return self._get_entities_basic(result, 'metric/')

    def list_facts(self):
        result = self.workspace_model.get_all_entities_facts(self.workspace_id, _check_return_type=False, size=100)
        return self._get_entities_basic(result, 'fact/')

    def list_insights(self):
        result = self.workspace_model.get_all_entities_visualization_objects(
            self.workspace_id, _check_return_type=False, size=100
        )
        return self._get_entities_basic(result)

    def get_label_title_by_id(self, label_id):
        result = self.workspace_model.get_entity_labels(self.workspace_id, label_id)
        return result.data['attributes']['title']

    def get_fact_title_by_id(self, fact_id):
        result = self.workspace_model.get_entity_facts(self.workspace_id, fact_id)
        return result.data['attributes']['title']

    def get_metric_title_by_id(self, metric_id):
        result = self.workspace_model.get_entity_metrics(self.workspace_id, metric_id)
        return result.data['attributes']['title']

    def invalid_caches(self, data_source_id):
        self.data_source_model.register_upload_notification(data_source_id)

    def scan_pdm(self, data_source_id, scan_tables=True, scan_views=True) -> ScanResultPdm:
        return self.scan_model.scan_pdm(
            data_source_id,
            scan_actions_api.ScanRequest(
                separator='__',
                scan_tables=scan_tables,
                scan_views=scan_views
            )
        )

    @staticmethod
    def is_primary_key(table, column, required_tables):
        if column.get('is_primary_key'):
            return True
        for required_table, table_data in required_tables.items():
            if table.path[-1] == required_table:
                if ('primary_key_column' in table_data) and (table_data['primary_key_column'] == column.name):
                    return True
        return False

    @staticmethod
    def get_reference_field(table, column, required_tables, field):
        if column.get(field):
            return column.get(field)
        for required_table, table_data in required_tables.items():
            if table.path[-1] == required_table:
                if 'references' in table_data:
                    for reference in table_data['references']:
                        if reference['source_column'] == column['name']:
                            return reference[field]
        return ''

    def scan_result_to_pdm(self, scan_result: ScanResultPdm, required_tables) -> DeclarativePdm:
        return DeclarativePdm(
            pdm=DeclarativeTables(
                tables=[
                    DeclarativeTable(
                        id=table.id,
                        path=table.path,
                        type=table.type,
                        columns=[
                            DeclarativeColumn(
                                name=column.name,
                                data_type=column.data_type,
                                is_primary_key=self.is_primary_key(table, column, required_tables),
                                referenced_table_id=self.get_reference_field(
                                    table, column, required_tables, 'referenced_table_id'
                                ),
                                referenced_table_column=self.get_reference_field(
                                    table, column, required_tables, 'referenced_table_column'
                                )
                            ) for column in table.columns
                        ]
                    ) for table in scan_result.pdm.tables if table.path[-1] in required_tables.keys()
                ]
            )
        )

    def store_pdm(self, data_source_id, pdm: DeclarativePdm):
        self.ds_layout.set_pdm_layout(data_source_id, pdm)

    def generate_ldm(self, data_source_id) -> DeclarativeLdm:
        return self.data_source_model.generate_logical_model(
            data_source_id,
            data_source_actions_controller_api.GenerateLdmRequest(
                separator='__',
                secondary_label_prefix='ls',
                date_granularities=''
            )
        )

    def store_ldm(self, workspace_id, ldm: DeclarativeLdm):
        self.ws_layout.set_logical_model(workspace_id, ldm)

    def create_or_update_data_source(
        self,
        data_source_id,
        data_source_name,
        ds_type,
        jdbc_url,
        schema_name,
        db_user,
        db_password,
        token=''
    ):
        document = JsonApiDataSourceInDocument(
            data=JsonApiDataSourceIn(
                id=data_source_id,
                attributes=JsonApiDataSourceInAttributes(
                    name=data_source_name,
                    type=ds_type,
                    url=jdbc_url,
                    schema=schema_name,
                    username=db_user or '',
                    password=db_password or '',
                    token=token
                )
            )
        )

        try:
            self.org_model.get_entity_data_sources(data_source_id)
            self.org_model.update_entity_data_sources(data_source_id, document, _check_return_type=False)
        except NotFoundException:
            self.org_model.create_entity_data_sources(document, _check_return_type=False)

    def create_or_update_workspace(self, workspace_id, workspace_name=None):
        document = JsonApiWorkspaceInDocument(
            data=JsonApiWorkspaceIn(
                id=workspace_id,
                attributes=(
                    JsonApiWorkspaceOutAttributes(
                        name=workspace_name or workspace_id
                    )
                )
            )
        )
        try:
            self.org_model.get_entity_workspaces(workspace_id)
            self.org_model.update_entity_workspaces(workspace_id, document, _check_return_type=False)
        except NotFoundException:
            self.org_model.create_entity_workspaces(document, _check_return_type=False)

    @staticmethod
    def beautify_from_id(object_id):
        return object_id[:1].upper() + re.sub(r'[^a-zA-Z0-9]', ' ', object_id[1:])

    @staticmethod
    def write_declarative_yaml(data, object_identifier, data_type):
        with open(f'gooddata/{data_type}_{object_identifier}.yml', 'w') as fp:
            yaml.dump(data, fp, indent=2, sort_keys=True)

    @staticmethod
    def read_declarative_yaml(object_identifier, data_type):
        with open(f'gooddata/{data_type}_{object_identifier}.yml') as fp:
            return yaml.load(fp)

    def register_data_source(self, config, dbt_output, gd_type, dbt_data_source):
        # TODO - now it works only for Postgres / Vertica
        self.create_or_update_data_source(
            data_source_id=dbt_output,
            data_source_name=self.beautify_from_id(dbt_output),
            ds_type=gd_type,
            jdbc_url='jdbc:{vendor}://{db_host}:{db_port}/{db_name}'.format(
                vendor=config.get_jdbc_vendor(dbt_data_source['type']),
                db_host=dbt_data_source['host'],
                db_port=dbt_data_source['port'],
                db_name=dbt_data_source.get('dbname', dbt_data_source.get('database'))
            ),
            schema_name=dbt_data_source['schema'],
            db_user=dbt_data_source.get('user', dbt_data_source.get('username')),
            db_password=dbt_data_source.get('pass', dbt_data_source.get('password')),
        )

    @staticmethod
    def filter_ldm_by_workspace_tables(ldm: DeclarativeLdm, workspace_tables):
        datasets = []
        for dataset in ldm.ldm.datasets:
            if dataset.data_source_table_id.id in workspace_tables.keys():
                datasets.append(dataset)
        ldm.ldm.datasets = datasets
        date_instances = []
        for date_instance in ldm.ldm.date_instances:
            for dataset in ldm.ldm.datasets:
                for reference in dataset.references:
                    if reference.identifier.id == date_instance.id:
                        date_instances.append(date_instance)
        ldm.ldm.date_instances = date_instances

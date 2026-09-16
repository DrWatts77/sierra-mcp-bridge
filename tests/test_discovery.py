import asyncio
import copy
import json

from fastmcp import Client
import pytest
from pydantic import ValidationError
from sierra_mcp_bridge.config import ChartConfig
from sierra_mcp_bridge.server import create_server
from test_history import add_history


def test_dynamic_discovery_names_history_removal(setup_bridge, raw):
    config, path, _ = setup_bridge
    config.charts[0].studies = []
    data = add_history(raw)
    data['exporter_revision'] = '1.4'
    data['studies'][0].update(study_name='Moving Average - Exponential', subgraph_name='Avg')
    path.write_text(json.dumps(data))

    async def check():
        async with Client(create_server(config)) as client:
            result = await client.call_tool('list_studies', {'chart_id': 'first'})
            assert result.structured_content['data'][0]['study_name'] == 'Moving Average - Exponential'
            second = dict(study_id=3, subgraph_index=0, value=101.0, reason=None,
                          study_name='Second "study" \\ name', subgraph_name='Output')
            data['studies'].append(second)
            for bar in data['history']:
                bar['studies'].append(copy.deepcopy(second))
            path.write_text(json.dumps(data))
            result = await client.call_tool('list_studies', {'chart_id': 'first'})
            assert [s['key'] for s in result.structured_content['data']] == ['id2_sg1', 'id3_sg1']
            for tool in ['get_study_values', 'get_study_history']:
                result = await client.call_tool(tool, {'chart_id': 'first', 'study_key': 'id3_sg1'})
                assert result.structured_content['data']['study_name'] == second['study_name']
            charts = await client.call_tool('list_charts')
            assert 'id3_sg1' in str(charts.structured_content)
            data['studies'].pop()
            for bar in data['history']:
                bar['studies'].pop()
            path.write_text(json.dumps(data))
            result = await client.call_tool('get_study_values', {'chart_id': 'first', 'study_key': 'id3_sg1'})
            assert result.structured_content['status'] == 'unavailable'
    asyncio.run(check())


def test_aliases_and_explicit_restriction(setup_bridge, raw):
    config, path, _ = setup_bridge
    config.charts[0].discover_exported_studies = False
    raw['studies'].append(dict(study_id=3, subgraph_index=0, value=12.0, reason=None))
    path.write_text(json.dumps(raw))

    async def check():
        async with Client(create_server(config)) as client:
            result = await client.call_tool('list_studies', {'chart_id': 'first'})
            assert len(result.structured_content['data']) == 1
            assert result.structured_content['data'][0]['study_name'] is None
            assert 'study_names_unavailable_rebuild_exporter' in result.structured_content['warnings']
            for key in ['ema', 'id2_sg1']:
                result = await client.call_tool('get_study_values', {'chart_id': 'first', 'study_key': key})
                assert result.structured_content['data']['value'] == 99.875
            result = await client.call_tool('get_study_values', {'chart_id': 'first', 'study_key': 'id3_sg1'})
            assert result.structured_content['status'] == 'unavailable'
    asyncio.run(check())


def test_alias_cannot_shadow_discovered_identity(setup_bridge):
    config, _, _ = setup_bridge
    chart = config.charts[0].model_dump()
    chart['studies'][0]['key'] = 'id3_sg1'
    with pytest.raises(ValidationError):
        ChartConfig.model_validate(chart)

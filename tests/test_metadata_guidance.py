import asyncio
import json

import pytest
from fastmcp import Client
from pydantic import ValidationError
from sierra_mcp_bridge.contracts import StudyMetadata
from sierra_mcp_bridge.server import create_server
from test_history import add_history


def metadata():
    return dict(short_name='Fast average', primary_color='#ffffff', secondary_color='#0000ff',
                secondary_color_used=False, latest_data_color_raw=None, draw_style_code=0,
                line_style_code=0, line_width=2, hide_study_setting_raw=0, graph_region_raw=0,
                inputs=[dict(index=0, name='Length', type_code=11, value=9, reason=None),
                        dict(index=1, name='Custom text', type_code=26, value=None, reason='unsupported_or_text_input')])


def test_metadata_discovery_value_history_and_startup(setup_bridge, raw):
    config, path, _ = setup_bridge
    data = add_history(raw)
    data['exporter_revision'] = '1.5'
    data['studies'][0].update(study_name='Moving Average - Exponential', metadata=metadata())
    path.write_text(json.dumps(data))

    async def check():
        async with Client(create_server(config)) as client:
            start = (await client.call_tool('get_startup_context')).structured_content
            assert start['charts'][0]['exported_study_count'] == 1
            assert start['charts'][0]['timeframe']['seconds_per_bar'] == 60
            assert not start['toolsets']['order_actions']['enabled']
            assert not start['toolsets']['account_reads']['tools']
            assert 'screenshot' in start['instructions']
            tools = {t.name for t in await client.list_tools()}
            assert {t for group in start['toolsets'].values() for t in group['tools']} == tools
            for tool in ['list_studies', 'get_study_values', 'get_study_history']:
                args = {'chart_id': 'first'}
                if tool != 'list_studies':
                    args['study_key'] = 'id2_sg1'
                result = (await client.call_tool(tool, args)).structured_content['data']
                if isinstance(result, list):
                    result = result[0]
                assert result['metadata']['primary_color'] == '#ffffff'
                assert result['metadata']['inputs'][0]['value'] == 9
                assert result['metadata']['inputs'][1]['value'] is None
    asyncio.run(check())


@pytest.mark.parametrize('field,value', [('primary_color', '#xx0000'), ('line_width', '2'),
                                      ('inputs', [dict(index=128, name='Length', type_code=11, value=9, reason=None)])])
def test_bad_metadata_rejected(field, value):
    with pytest.raises(ValidationError):
        StudyMetadata.model_validate({**metadata(), field: value})

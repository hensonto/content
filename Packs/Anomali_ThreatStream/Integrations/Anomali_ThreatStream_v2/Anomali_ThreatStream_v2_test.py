import os
import json
import demistomock as demisto
from tempfile import mkdtemp
from Anomali_ThreatStream_v2 import main, file_name_to_valid_string, get_file_reputation, Client, get_indicators, \
    build_context_indicator_no_results_status
import emoji
import pytest


def util_load_json(path):
    with open(path, mode='r', encoding='utf-8') as f:
        return json.loads(f.read())


def http_request_with_approval_mock(req_type, suffix, params, data=None, files=None):
    return {
        'success': True,
        'import_session_id': params,
        'data': data,
    }


def http_request_without_approval_mock(req_type, suffix, params, data=None, files=None, json=None, text_response=None):
    return {
        'success': True,
        'import_session_id': 1,
        'files': files
    }


package_500_error = {
    'import_type': 'url',
    'import_value': 'www.demisto.com',
}

expected_output_500 = {
    'Contents': {
        'data': {
            'classification': 'Private',
            'confidence': 50,
            'severity': 'low',
            'threat_type': 'exploit',
            'url': 'www.demisto.com'
        },
        'import_session_id': {
            'api_key': None,
            'username': None
        },
        'success': True
    },
    'ContentsFormat': 'json',
    'EntryContext': {
        'ThreatStream.Import.ImportID': {
            'api_key': None,
            'datatext': 'www.demisto.com',
            'username': None
        }
    },
    'HumanReadable': 'The data was imported successfully. The ID of imported job '
                     "is: {'datatext': 'www.demisto.com', 'username': None, "
                     "'api_key': None}",
    'Type': 1
}

mock_objects = {"objects": [{"srcip": "8.8.8.8", "itype": "mal_ip", "confidence": 50},
                            {"srcip": "1.1.1.1", "itype": "apt_ip"}]}

expected_import_json = {'objects': [{'srcip': '8.8.8.8', 'itype': 'mal_ip', 'confidence': 50},
                                    {'srcip': '1.1.1.1', 'itype': 'apt_ip'}],
                        'meta': {'classification': 'private', 'confidence': 30, 'allow_unresolved': False}}

INDICATOR = [{
    "resource_uri": "/api/v2/intelligence/123456789/",
    "status": "active",
    "uuid": "12345678-dead-beef-a6cc-eeece19516f6",
    "value": "www.demisto.com",
}]


def test_ioc_approval_500_error(mocker):
    mocker.patch.object(Client, 'http_request', side_effect=http_request_with_approval_mock)
    mocker.patch.object(demisto, 'args', return_value=package_500_error)
    mocker.patch.object(demisto, 'command', return_value='threatstream-import-indicator-with-approval')
    mocker.patch.object(demisto, 'results')

    main()
    results = demisto.results.call_args[0]

    assert results[0]['Contents']['data'] == expected_output_500['Contents']['data']


def test_emoji_handling_in_file_name():
    file_names_package = ['Fwd for you 😍', 'Hi all', '', '🐝🤣🇮🇱👨🏽‍🚀🧟‍♂🧞‍♂🧚🏼‍♀', '🧔🤸🏻‍♀🥩🧚😷🍙👻']

    for file_name in file_names_package:
        demojized_file_name = file_name_to_valid_string(file_name)
        assert demojized_file_name == emoji.demojize(file_name)
        assert not emoji.emoji_count(file_name_to_valid_string(demojized_file_name))


def test_import_ioc_without_approval(mocker):
    tmp_dir = mkdtemp()
    file_name = 'test_file.txt'
    file_obj = {
        'name': file_name,
        'path': os.path.join(tmp_dir, file_name)
    }
    with open(file_obj['path'], 'w') as f:
        json.dump(mock_objects, f)
    http_mock = mocker.patch.object(Client, 'http_request', side_effect=http_request_without_approval_mock)
    mocker.patch.object(demisto, 'args', return_value={'file_id': 1, 'classification': 'private',
                                                       'allow_unresolved': 'no', 'confidence': 30})
    mocker.patch.object(demisto, 'command', return_value='threatstream-import-indicator-without-approval')
    mocker.patch.object(demisto, 'results')
    mocker.patch.object(demisto, 'getFilePath', return_value=file_obj)

    main()
    results = demisto.results.call_args[0]

    assert results[0]['Contents']
    assert expected_import_json == http_mock.call_args[1]['json']


SHA_256_FILE_HASH = '178ba564b39bd07577e974a9b677dfd86ffa1f1d0299dfd958eb883c5ef6c3e1'
SHA_512_FILE_HASH = '665564674b6b4a7a3a69697221acef98ee5ca3664ce6b370059cb7d3b0942589556e5a9d69d83d038339535ea4ced2d4d' \
                    '300e07013a16'


@pytest.mark.parametrize('file_hash, expected_result_file_path, raw_response_file_path', [
    (SHA_256_FILE_HASH,
     'test_data/file_256_context.json',
     'test_data/file_256_response.json'),
    (SHA_512_FILE_HASH,
     'test_data/file_512_context.json',
     'test_data/file_512_response.json')
])
def test_get_file_reputation(mocker, file_hash, expected_result_file_path, raw_response_file_path):
    expected_result = util_load_json(expected_result_file_path)
    raw_response = util_load_json(raw_response_file_path)
    mocker.patch('Anomali_ThreatStream_v2.search_indicator_by_params', return_value=raw_response)
    mocker.patch.object(demisto, 'results')

    client = Client(
        base_url='',
        use_ssl=False,
        default_threshold='high',
        reliability='B - Usually reliable'
    )

    get_file_reputation(client, file_hash)
    context = demisto.results.call_args_list[0][0][0].get('EntryContext')

    assert context == expected_result


class TestGetIndicators:
    @staticmethod
    def test_sanity(mocker):
        """
        Given
            a limit above the number of available indicators
        When
            calling the get_indicator command
        Then
            verify that the maximum available amount is returned.
        """
        mocker.patch.object(Client, 'http_request', side_effect=[
            {'objects': INDICATOR * 50},
            {'objects': []},
        ])
        results = mocker.patch.object(demisto, 'results')
        client = Client(
            base_url='',
            use_ssl=False,
            default_threshold='high',
            reliability='B - Usually reliable',
        )

        get_indicators(client, limit='7000')

        assert len(results.call_args_list[0][0][0].get('EntryContext', {}).get('ThreatStream.Indicators', [])) == 50

    @staticmethod
    def test_pagination(mocker):
        """
        Given
            a limit above the page size
        When
            calling the get_indicator command
        Then
            verify that the requested amount is returned.
        """
        mocker.patch.object(Client, 'http_request', side_effect=[
            {'objects': INDICATOR * 1000},
            {'objects': INDICATOR * 1000},
            {'objects': INDICATOR * 1000},
            {'objects': INDICATOR * 1000},
            {'objects': INDICATOR * 1000},
            {'objects': INDICATOR * 1000},
            {'objects': INDICATOR * 1000},
        ])
        results = mocker.patch.object(demisto, 'results')
        client = Client(
            base_url='',
            use_ssl=False,
            default_threshold='high',
            reliability='B - Usually reliable',
        )

        get_indicators(client, limit='7000')

        assert len(results.call_args_list[0][0][0].get('EntryContext', {}).get('ThreatStream.Indicators', [])) == 7000


DBOT_SCORE_UNKNOWN = [

    (
        {'indicator': 'd26cec10398f2b10202d23c966022dce', 'indicator_type': 'file',
         'integration_name': 'test', 'message': 'Not found'},
        {'indicator': 'd26cec10398f2b10202d23c966022dce', 'indicator_type': 'file', 'message': 'Not found',
         'sha1': None, 'sha256': None, 'md5': 'd26cec10398f2b10202d23c966022dce'}
    ),
    (
        {'indicator': 'f4dad67d0f0a8e53d87fc9506e81b76e043294da77ae50ce4e8f0482127e7c12', 'indicator_type': 'file',
         'integration_name': 'test', 'message': 'Not found'},
        {'indicator': 'f4dad67d0f0a8e53d87fc9506e81b76e043294da77ae50ce4e8f0482127e7c12', 'indicator_type': 'file',
         'message': 'Not found', 'sha1': None,
         'sha256': 'f4dad67d0f0a8e53d87fc9506e81b76e043294da77ae50ce4e8f0482127e7c12', 'md5': None}
    ),
    (
        {'indicator': 'cf23df2207d99a74fbe169e3eba035e633b65d94', 'indicator_type': 'file',
         'integration_name': 'test', 'message': 'Not found'},
        {'indicator': 'cf23df2207d99a74fbe169e3eba035e633b65d94', 'indicator_type': 'file',
         'message': 'Not found', 'sha1': 'cf23df2207d99a74fbe169e3eba035e633b65d94', 'sha256': None, 'md5': None}
    ),
    (
        {'indicator': '8.8.8.8', 'indicator_type': 'ip', 'integration_name': 'test', 'message': 'Not found'},
        {'indicator': '8.8.8.8', 'indicator_type': 'ip',
         'message': 'Not found'}
    ),
    (
        {'indicator': 'www.example.com', 'indicator_type': 'url', 'integration_name': 'test', 'message': 'Not found'},
        {'indicator': 'www.example.com', 'indicator_type': 'url', 'message': 'Not found'}
    ),
    (
        {'indicator': 'example.com', 'indicator_type': 'domain', 'integration_name': 'test', 'message': 'Not found'},
        {'indicator': 'example.com', 'indicator_type': 'domain', 'message': 'Not found'}
    )
]


@pytest.mark.parametrize('inputs, expected_return', DBOT_SCORE_UNKNOWN)
def test_build_context_indicator_no_results_status(inputs, expected_return):

    results = build_context_indicator_no_results_status(indicator=inputs.get('indicator'),
                                                        indicator_type=inputs.get('indicator_type'),
                                                        integration_name='test',
                                                        message=inputs.get('message'))

    assert results.readable_output == expected_return.get('message')
    assert results.indicator.dbot_score.score == 0
    assert results.indicator.dbot_score.indicator_type == expected_return.get('indicator_type')
    if results.indicator.dbot_score.indicator_type == 'file':
        assert results.indicator.sha1 == expected_return.get('sha1')
        assert results.indicator.sha256 == expected_return.get('sha256')
        assert results.indicator.md5 == expected_return.get('md5')

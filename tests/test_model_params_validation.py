import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'middleware'))

import core.config as config



def test_load_model_params_warns_when_image_model_capability_is_incomplete(tmp_path, monkeypatch, caplog):
    config_dir = tmp_path / 'config'
    config_dir.mkdir()
    (config_dir / 'model_params.yaml').write_text(
        '\n'.join([
            'image_model:',
            '  providers:',
            '    broken-model:',
            '      capability:',
            '        prompt_policy: reference_first',
        ]),
        encoding='utf-8',
    )

    monkeypatch.setattr(config, '_CONFIG_DIR', config_dir)

    with caplog.at_level('WARNING'):
        loaded = config.load_model_params()

    assert loaded['image_model']['providers']['broken-model']['capability']['prompt_policy'] == 'reference_first'
    assert "broken-model missing capability keys: ['adapter_family', 'generation_size_key', 'primary_reference_mode', 'reference_input_mode', 'sub_prompt_identity_lock']" in caplog.text



def test_load_model_params_warns_when_image_model_capability_is_missing(tmp_path, monkeypatch, caplog):
    config_dir = tmp_path / 'config'
    config_dir.mkdir()
    (config_dir / 'model_params.yaml').write_text(
        '\n'.join([
            'image_model:',
            '  providers:',
            '    missing-capability-model:',
            '      endpoint: https://example.com',
        ]),
        encoding='utf-8',
    )

    monkeypatch.setattr(config, '_CONFIG_DIR', config_dir)

    with caplog.at_level('WARNING'):
        loaded = config.load_model_params()

    assert loaded['image_model']['providers']['missing-capability-model']['endpoint'] == 'https://example.com'
    assert "missing-capability-model capability must be a dict" in caplog.text



def test_load_model_params_does_not_warn_for_complete_image_model_capability(tmp_path, monkeypatch, caplog):
    config_dir = tmp_path / 'config'
    config_dir.mkdir()
    (config_dir / 'model_params.yaml').write_text(
        '\n'.join([
            'image_model:',
            '  providers:',
            '    healthy-model:',
            '      capability:',
            '        prompt_policy: reference_first',
            '        sub_prompt_identity_lock: false',
            '        primary_reference_mode: reference_image',
            '        adapter_family: openai',
            '        reference_input_mode: input_image',
            '        generation_size_key: size',
        ]),
        encoding='utf-8',
    )

    monkeypatch.setattr(config, '_CONFIG_DIR', config_dir)

    with caplog.at_level('WARNING'):
        loaded = config.load_model_params()

    assert loaded['image_model']['providers']['healthy-model']['capability']['primary_reference_mode'] == 'reference_image'
    assert 'missing capability keys' not in caplog.text
    assert 'capability must be a dict' not in caplog.text

from pathlib import Path

path = Path('tests/application/test_column_public_a5_product_path.py')
text = path.read_text(encoding='utf-8')
old_import = 'import tbdy_engine.application.column_public_a5 as a5\nimport tbdy_engine.application.project_execution as project_execution\n'
new_import = 'import tbdy_engine.application.column_public_a5 as a5\nimport tbdy_engine.application.column_execution as column_execution\nimport tbdy_engine.application.project_execution as project_execution\n'
if old_import not in text:
    raise SystemExit('column_execution import anchor missing')
text = text.replace(old_import, new_import, 1)
old_patch = '    monkeypatch.setattr(project_execution, "EtabsVerifiedSession", _FakeSession)\n    monkeypatch.setattr(project_execution, "create_trusted_live_acquisition_context", lambda verified_session: context)\n'
new_patch = '    monkeypatch.setattr(project_execution, "EtabsVerifiedSession", _FakeSession)\n    monkeypatch.setattr(project_execution, "create_trusted_live_acquisition_context", lambda verified_session: context)\n    monkeypatch.setattr(column_execution, "TrustedLiveAcquisitionContext", _FakeContext)\n'
if old_patch not in text:
    raise SystemExit('column_execution monkeypatch anchor missing')
path.write_text(text.replace(old_patch, new_patch, 1), encoding='utf-8')
Path(__file__).unlink()

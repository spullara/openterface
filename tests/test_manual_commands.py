import pytest
from kvmuse import unlock, keep_awake


class FakeDriver:
    def __init__(self):
        self.events = []
    def key_press(self, keys, modifiers=0):
        self.events.append(('key', keys, modifiers))
    def key_release_all(self):
        self.events.append(('release',))
    def type_text(self, text):
        self.events.append(('text', text))


def key(keys, modifiers=0):
    return [('key', keys, modifiers), ('release',)]


def test_sequences(monkeypatch, capsys):
    monkeypatch.setattr(unlock.time, 'sleep', lambda _: None)
    driver = FakeDriver()
    unlock.unlock(driver, 'Fake-only!')
    assert driver.events == (key([], 2) + key(['a'], 8) + key(['backspace'])
                             + [('text', 'Fake-only!')] + key(['enter']))
    driver.events.clear()
    keep_awake.keep_awake(driver, 'Fake-only!')
    expected = key(['space'], 8) + [('text', 'Terminal')] + key(['enter']) + key(['n'], 8)
    for text in ['sudo -k', keep_awake.POWER, 'Fake-only!', keep_awake.SCREENSAVER, keep_awake.CHECK]:
        expected += [('text', text)] + key(['enter'])
    assert driver.events == expected
    assert 'Fake-only!' not in str(capsys.readouterr())


@pytest.mark.parametrize('password', ['', 'fakeé', 'fake\n', 'fake\t'])
@pytest.mark.parametrize('command', [unlock.unlock, keep_awake.keep_awake])
def test_validation_before_input(command, password):
    driver = FakeDriver()
    with pytest.raises(ValueError):
        command(driver, password)
    assert driver.events == []


def test_dry_run_never_opens_or_prompts(monkeypatch):
    def fail(*args):
        pytest.fail('Dry run touched hardware or password prompt')
    monkeypatch.setattr(keep_awake, 'CH9329', fail)
    monkeypatch.setattr(keep_awake, 'read_password', fail)
    assert keep_awake.main(['--dry-run']) == 0


@pytest.mark.parametrize('module', [unlock, keep_awake])
def test_error_does_not_print_password(module, monkeypatch, capsys):
    monkeypatch.setattr(module, 'read_password', lambda: 'Fake-only!')
    def fail(*args):
        raise RuntimeError('Fake-only!')
    monkeypatch.setattr(module, 'CH9329', fail)
    assert module.main([]) == 1
    assert 'Fake-only!' not in str(capsys.readouterr())


def test_no_echo_fallback(monkeypatch):
    import warnings
    def fallback(*args):
        warnings.warn('no tty', unlock.getpass.GetPassWarning)
        pytest.fail('Echo fallback permitted')
    monkeypatch.setattr(unlock.getpass, 'getpass', fallback)
    with pytest.raises(unlock.getpass.GetPassWarning):
        unlock.read_password()

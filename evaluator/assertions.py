def assert_verified(result: dict) -> None:
    assert result.get('status') == 'VERIFIED', result
    verification = result.get('verification') or {}
    assert verification.get('passed') is True, verification
    assert not verification.get('violations'), verification

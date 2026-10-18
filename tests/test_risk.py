from deltabot.risk import MonthlyStop, size_lots


def test_size_lots_margin_and_risk_cap():
    assert size_lots(500, 8.0) == 62
    assert size_lots(500, 8.0, max_loss_per_lot=1.25, risk_fraction=0.10) == 40
    assert size_lots(0, 8.0) == 0


def test_monthly_stop_resets_each_month():
    stop = MonthlyStop(0.10)
    assert stop.allowed("2026-03", 500)
    assert stop.allowed("2026-03", 460)
    assert not stop.allowed("2026-03", 450)  # down 10%: done for March
    assert stop.allowed("2026-04", 500)      # fresh month

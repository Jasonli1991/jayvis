import bot


def test_group_mention_non_allowlist_gets_reply():
    """群組裡被 @ 但發話者不在白名單 → 回一句婉拒（不再靜默）。"""
    assert bot.non_allowlist_reply("group") == "我無法接受您的指令喔🥹"
    assert bot.non_allowlist_reply("supergroup") == "我無法接受您的指令喔🥹"


def test_private_non_allowlist_stays_silent():
    """私訊陌生人 → 仍靜默（不主動回應，避免被陌生人/垃圾訊息纏上）。"""
    assert bot.non_allowlist_reply("private") is None

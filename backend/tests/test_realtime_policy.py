from app.voice.realtime_policy import receptionist_instructions


def test_realtime_policy_prevents_repeated_introductions_and_unnatural_delivery() -> None:
    policy = receptionist_instructions(
        "Geeta Medicine",
        timezone="Asia/Kolkata",
        local_time="Saturday, 13 September 2026, 09:30 AM",
        pronunciation_guidance="Say Geeta softly",
        caller_profile={
            "ok": True,
            "recognized": True,
            "caller_name": "Aryan Gupta",
            "family_profiles": [
                {"patient_name": "Aryan Gupta", "relationship": "SELF"},
                {"patient_name": "Bibha Gupta", "relationship": "MOTHER"},
            ],
        },
    )

    assert "Introduce yourself only once" in policy
    assert (
        '"Geeta Medicine mein aapka swagat hai. '
        'Batayiye, main aapki kya madad kar sakti hoon?"' in policy
    )
    assert "Default to natural Hindi/Hinglish" in policy
    assert "Stay in Hindi/Hinglish unless the caller clearly uses English" in policy
    assert "English returned by a tool is not a reason" in policy
    assert "to switch the whole conversation to English" in policy
    assert "steady conversational pace" in policy
    assert "Keep pitch and volume stable" in policy
    assert "Do not claim success before the backend confirms" in policy
    assert "Geeta Medicine" in policy
    assert "Asia/Kolkata" in policy
    assert "Saturday, 13 September 2026, 09:30 AM" in policy
    assert "Ji, main check karti hoon" in policy
    assert "A short natural acknowledgement" in policy
    assert "Recognized caller name: Aryan Gupta" in policy
    assert "MOTHER: Bibha Gupta" in policy
    assert "Caller lookup has already completed" in policy
    assert "Other relationships → OTHER" in policy
    assert "The caller does NOT have to provide information in a fixed order" in policy
    assert "When the caller provides enough information" in policy
    assert "If the caller clearly names a specialty or department" in policy
    assert "do NOT use suggest_department" in policy
    assert "PATIENT INFORMATION CAN ARRIVE AT ANY TIME" in policy
    assert "After doctor and slot are selected" in policy
    assert "NEVER ask the caller for information" in policy
    assert "list_upcoming_appointments" in policy
    assert "confirm_booking" not in policy

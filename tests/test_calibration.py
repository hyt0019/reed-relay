from reed_relay.core.calibration import GuidedCalibration
from reed_relay.core.profile import Profile


PITCHES = [62,64,66,67,69,71,73,74]
SHIFTS = [-12,1,12]


def arm(guide, now):
    guide.tick(now,set(),True)
    guide.tick(now+.8,set(),True)
    return now+.8


def measure(guide, now, pitch, held=None):
    held = guide.expected if held is None else held
    guide.tick(now,held,True)
    for delta in (.5,.75,1.):
        guide.tick(now+delta,held,True,{"frequency":440,"pitch":pitch,"cents":0})
    return now+1.


def test_complete_calibration_changes_only_copy_and_cross_checks_modifiers():
    original=Profile()
    guide=GuidedCalibration(original,0)
    now=arm(guide,4)
    assert len(guide.steps)==18
    while guide.active:
        step=guide.step
        pitch=PITCHES[step.base]+sum(SHIFTS[i] for i in step.modifiers)
        now=measure(guide,now,pitch)
        assert guide.phase=="release"
        now=arm(guide,now+.1)
    assert guide.phase=="done"
    assert guide.result.pitches==PITCHES
    assert [m.semitones for m in guide.result.modifiers]==SHIFTS
    assert guide.result.calibrated
    assert original.pitches!=PITCHES and not original.calibrated


def test_no_advance_for_wrong_keys_unstable_tone_or_unfocused_game():
    guide=GuidedCalibration(Profile(),0)
    now=arm(guide,4)
    now=measure(guide,now,60,held={"X"})
    assert not guide.values
    guide.tick(now+.1,{"Z"},False,{"frequency":440,"pitch":60,"cents":0})
    assert not guide.values
    now=arm(guide,now+1)
    guide.tick(now,{"Z"},True)
    for i,pitch in enumerate([60,61,60,61]):
        guide.tick(now+.5+i*.25,{"Z"},True,{"frequency":440,"pitch":pitch,"cents":0})
    assert not guide.values
    guide.tick(now+2,{"Z"},True,{"frequency":440,"pitch":60,"cents":45})
    assert not guide.samples


def test_repeated_ticks_do_not_reuse_audio_and_release_is_required():
    guide=GuidedCalibration(Profile(),0)
    now=arm(guide,4)
    guide.tick(now,{"Z"},True)
    guide.tick(now+.5,{"Z"},True,{"frequency":440,"pitch":60,"cents":0})
    for i in range(20): guide.tick(now+.6+i*.05,{"Z"},True)
    assert not guide.values
    now=measure(guide,now+2,60)
    guide.tick(now+2,{"Z"},True)
    assert guide.index==0 and guide.phase=="release"
    now=arm(guide,now+3)
    assert guide.index==1


def test_pause_rewind_and_cancel_discard_derived_steps():
    guide=GuidedCalibration(Profile(),0)
    now=arm(guide,4)
    now=measure(guide,now,60)
    now=arm(guide,now+.1)
    guide.toggle_pause()
    now=measure(guide,now,62)
    assert 1 not in guide.values
    guide.toggle_pause()
    guide.rewind()
    assert guide.index==0 and not guide.values
    guide.cancel()
    assert not guide.active and guide.result is None


def test_optional_combo_failure_and_skip_never_enable_unverified_combo():
    guide=GuidedCalibration(Profile(),0)
    now=arm(guide,4)
    while guide.index<14:
        step=guide.step
        now=measure(guide,now,PITCHES[step.base]+sum(SHIFTS[i] for i in step.modifiers))
        now=arm(guide,now+.1)
    now=measure(guide,now,PITCHES[0])
    assert 14 not in guide.values and "组合" in guide.hint
    guide.skip(now)
    now=arm(guide,now+.1)
    while guide.active:
        step=guide.step
        now=measure(guide,now,PITCHES[step.base]+sum(SHIFTS[i] for i in step.modifiers))
        now=arm(guide,now+.1)
    assert [0,1] not in guide.result.combinations
    assert [1,2] in guide.result.combinations


def test_modifier_cross_check_failure_cannot_finish_or_skip():
    guide=GuidedCalibration(Profile(),0)
    now=arm(guide,4)
    while guide.index<9:
        step=guide.step
        now=measure(guide,now,PITCHES[step.base]+sum(SHIFTS[i] for i in step.modifiers))
        now=arm(guide,now+.1)
    now=measure(guide,now,PITCHES[1]-11)
    assert 9 not in guide.values and "不一致" in guide.hint
    guide.skip(now)
    assert guide.index==9 and "不能跳过" in guide.hint


def test_custom_keys_and_no_combos_produce_matching_instructions():
    profile=Profile(keys=list("ASDFGHJK"), combinations=[[],[0],[1],[2]])
    guide=GuidedCalibration(profile,0)
    assert len(guide.steps)==14
    assert guide.expected=={"A"}
    assert guide.instruction()=="A"

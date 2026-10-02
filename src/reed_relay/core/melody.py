"""Temporal melody selection and explicit, reversible fragment repair."""
from dataclasses import replace
from .score import Note, number


def select_melody(notes: list[Note]) -> list[Note]:
    """Choose a path through active candidates, charging for pitch switches.

    A brief competing activation must earn its switch over time. Candidate
    silence remains silence; this does not infer missing vocal notes.
    """
    starts, ends = {}, {}
    for note in notes:
        starts.setdefault(round(note.start_ms, 3), []).append(note)
        ends.setdefault(round(note.end_ms, 3), []).append(note)
    times = sorted(starts.keys() | ends.keys())
    active, states, result = {}, {}, []

    def finish():
        if not states:
            return
        node = max(states.values(), key=lambda state: state[0])[1]
        path = []
        while node:
            note, start, end, previous = node
            path.append((note, start, end))
            node = previous
        previous_id = None
        for note, start, end in reversed(path):
            if result and previous_id == note.id and abs(result[-1].end_ms-start) < .01:
                result[-1] = replace(result[-1], duration_ms=end-result[-1].start_ms)
            else:
                result.append(replace(note, start_ms=start, duration_ms=end-start,
                                      id=f"{note.id}:melody:{len(result)}"))
            previous_id = note.id

    for index, start in enumerate(times[:-1]):
        for note in ends.get(start, []):
            active.pop(note.id, None)
        for note in starts.get(start, []):
            active[note.id] = note
        end = times[index+1]
        if not active:
            finish()
            states = {}
            continue
        if end-start < .1:
            continue
        next_states = {}
        for note in active.values():
            emission = (end-start)/1000 * (note.confidence + note.midi_pitch*.0015)
            if states:
                def transition(state):
                    previous = state[1][0]
                    distance = abs(note.midi_pitch-previous.midi_pitch)
                    cost = (.055 + min(distance, 24)*.004) if distance else (0 if note.id == previous.id else .005)
                    return state[0]-cost
                best = max(states.values(), key=transition)
                value, previous_node = transition(best)+emission, best[1]
            else:
                value, previous_node = emission, None
            next_states[note.id] = (value, (note, start, end, previous_node))
        states = next_states
    finish()
    return result


def repair_melody(notes: list[Note], minimum_ms=80., gap_ms=50., merge_repeats=False) -> list[Note]:
    """Repair a monophonic draft without shifting later onsets or its key.

    Short notes are removed explicitly, not stretched over their neighbours.
    Only bounded gaps are filled. Intentional same-pitch attacks are preserved
    unless the user requests merging repeated notes.
    """
    number(minimum_ms, "碎音阈值", 0, 500)
    number(gap_ms, "衔接间隙", 0, 250)
    ordered = sorted(notes, key=lambda note: (note.start_ms, note.midi_pitch))
    if any(a.end_ms > b.start_ms+.01 for a, b in zip(ordered, ordered[1:])):
        ordered = select_melody(ordered)
    kept = [note for note in ordered if note.duration_ms+.001 >= minimum_ms]
    result = []
    for note in kept:
        if result:
            previous = result[-1]
            gap = note.start_ms-previous.end_ms
            if -.01 <= gap <= gap_ms+.001:
                # Same original candidate fragments can safely be reunited.
                def origin(identifier):
                    if ':melody:' in identifier:
                        return identifier.rsplit(':melody:', 1)[0]
                    head, separator, tail = identifier.rpartition('_')
                    if separator and len(head) == 12 and all(c in '0123456789abcdef' for c in head) and tail.isdigit():
                        return head
                    return identifier
                same_origin = origin(previous.id) == origin(note.id)
                if previous.midi_pitch == note.midi_pitch and previous.cents == note.cents and (merge_repeats or same_origin):
                    result[-1] = replace(previous, duration_ms=note.end_ms-previous.start_ms)
                    continue
                if gap > 0:
                    result[-1] = replace(previous, duration_ms=note.start_ms-previous.start_ms)
        result.append(note)
    return result

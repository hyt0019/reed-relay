"""Temporal melody selection and explicit, reversible fragment repair."""
from dataclasses import replace
from .score import Note, number


def select_melody(notes: list[Note], *, minimum_pitch=0, maximum_pitch=127) -> list[Note]:
    """Follow a melodic register with explicit silence and switch costs.

    Register is estimated from nearby sustained candidates, not the game's
    playable range. A strong bass or brief high ornament must not win simply
    by activation or pitch. Filtering never transposes or invents notes.
    """
    number(minimum_pitch, "旋律最低音", 0, 127)
    number(maximum_pitch, "旋律最高音", minimum_pitch, 127)
    notes = sorted((n for n in notes if minimum_pitch <= n.midi_pitch <= maximum_pitch),
                   key=lambda n: (n.start_ms, n.midi_pitch, n.id))
    if not notes or all(a.end_ms <= b.start_ms+.01 for a, b in zip(notes, notes[1:])):
        return list(notes)
    registers = {}

    def register(at_ms):
        bucket = int(at_ms // 1000)
        if bucket not in registers:
            center = bucket*1000+500
            nearby = []
            for candidate in notes:
                if candidate.start_ms >= center+4000: break
                if candidate.end_ms <= center-4000: continue
                weight = min(candidate.duration_ms, 500) * max(.1, candidate.confidence)
                weight *= min(1., candidate.duration_ms/150)**3
                nearby.append((candidate.midi_pitch, weight))
            threshold = sum(weight for _, weight in nearby)*.9
            running = 0.
            for pitch, weight in sorted(nearby):
                running += weight
                if running >= threshold:
                    registers[bucket] = pitch
                    break
        return registers[bucket]

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
            if note is None:
                previous_id = None
                continue
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
        target = register((start+end)/2)
        for note in [None, *active.values()]:
            if note is None:
                emission = 0.
            else:
                utility = .45 + note.confidence*.5
                utility -= max(0, target-note.midi_pitch-4)*.075
                utility -= max(0, note.midi_pitch-target-7)*.04
                utility -= max(0, 1-note.duration_ms/100)*.9
                emission = (end-start)/1000 * utility
            if states:
                def transition(state):
                    previous = state[2]
                    if note is None:
                        cost = .025 if state[1][0] is not None else 0.
                    elif previous is None:
                        cost = .04
                    else:
                        distance = abs(note.midi_pitch-previous.midi_pitch)
                        cost = (.06 + min(distance, 24)*.006) if distance else (0 if note.id == previous.id else .008)
                        # Avoid entering an already sounding accompaniment halfway.
                        if note.id != previous.id and start-note.start_ms > 60: cost += .18
                    return state[0]-cost
                best = max(states.values(), key=transition)
                value, previous_node = transition(best)+emission, best[1]
                last = note if note is not None else best[2]
            else:
                value, previous_node, last = emission, None, note
            next_states[note.id if note else None] = (value, (note, start, end, previous_node), last)
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

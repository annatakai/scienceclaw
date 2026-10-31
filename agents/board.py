"""The shared board: the only channel between agents."""


class Board:
    def __init__(self):
        self.messages = []

    def add(self, year, rnd, frm, typ, seg, text, payload=None):
        m = dict(msg_id=len(self.messages) + 1, year=year, round=rnd, **{"from": frm}, type=typ,
                 segment_id=seg, text=text, payload=payload or {})
        self.messages.append(m)
        return m

    def get(self, year, rnd, frm, typ):
        return [m for m in self.messages if m["year"] == year and m["round"] == rnd and m["from"] == frm
                and m["type"] == typ]


def bundle_id(year, seg):
    return f"B-{year}-{seg}"

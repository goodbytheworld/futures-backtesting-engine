"""
FastBar data structure for bar-by-bar backtesting.
"""

class FastBar:
    __slots__ = ['name', 'open', 'high', 'low', 'close', 'volume', '_dict']
    def __init__(self, name, o, h, l, c, v):
        self.name = name
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.volume = v
        self._dict = {'open': o, 'high': h, 'low': l, 'close': c, 'volume': v}

    def __getitem__(self, key):
        return self._dict[key]

    def get(self, key, default=None):
        return self._dict.get(key, default)

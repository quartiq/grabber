bitseq = (0, 1, 2, 3, 4, 6, 27, 5, 7, 8, 9,
        12, 13, 14, 10, 11, 15, 18, 19, 20, 21, 22, 16, 17)
assert len(set(bitseq)) == len(bitseq)


def encode(data, fval=1, lval=1, dval=1, spare=0):
    return ((lval << 24) | (fval << 25) | (dval << 26) | (spare << 23) |
            sum(((data >> i) & 1) << j for i, j in enumerate(bitseq)))

def decode(cl):
    data = sum(((cl >> j) & 1) << i for i, j in enumerate(bitseq))
    lval, fval, dval, spare = ((cl >> i) & 1 for i in (24, 25, 26, 23))
    return data, fval, lval, dval, spare


class Frame:
    vblank = 3
    hblank = 2

    def __init__(self, data):
        self.data = data

    def gen_line(self, line, fval=1):
        for i in range(self.hblank):
            yield encode(line[0], fval=fval, lval=0, dval=0)
        for i in line:
            yield encode(i, fval=fval, dval=fval)

    def gen_frame(self):
        for i in range(self.vblank):
            yield from self.gen_line(self.data[0], fval=0)
        for i in self.data:
            yield from self.gen_line(i)


if __name__ == "__main__":
    f = Frame([[i*4 + j for j in range(4)] for i in range(3)])

    for i in f.gen_frame():
        j = decode(i)
        print(j)

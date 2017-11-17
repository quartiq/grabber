from migen import *

import cameralink


class Parser(Module):
    def __init__(self, width):
        self.cl = cl = Signal(28)

        self.pix = pix = Record([
            ("x", width),
            ("y", width),
            ("a", 8),
            ("b", 8),
            ("c", 8),
            ("stb", 1),
            ("eop", 1),
        ])

        ###

        lval = Signal()
        fval = Signal()
        dval = Signal()
        self.comb += [
                Cat(lval, fval, dval).eq(cl[24:]),
                pix.stb.eq(dval),
                pix.eop.eq(~fval),
                Cat(pix.a, pix.b, pix.c).eq(
                    Cat(cl[i] for i in cameralink.bitseq)),
        ]
        last_lval = Signal()
        last_fval = Signal()
        self.sync += [
                last_lval.eq(lval),
                last_fval.eq(fval),
                pix.x.eq(pix.x + 1),
                If(~lval,
                    pix.x.eq(0),
                    If(last_fval & last_lval,
                        pix.y.eq(pix.y + 1),
                    ),
                ),
                If(~fval,
                    pix.y.eq(0),
                ),
        ]

    def test(self, frame, ret):
        for i in frame:
            yield self.cl.eq(i)
            yield
            x = (yield self.pix.x)
            y = (yield self.pix.y)
            dval = (yield self.pix.stb)
            a = (yield self.pix.a)
            b = (yield self.pix.b)
            c = (yield self.pix.c)
            data0, fval0, lval0, dval0, spare0 = cameralink.decode(i)
            assert data0 == a | (b << 8) | (c << 16)
            assert dval == dval0
            if (yield self.pix.stb):
                ret.append(((x, y), (a, b, c)))
        yield self.cl.eq(0)


class ROI(Module):
    def __init__(self, pix, shift=0):
        self.cfg = cfg = Record([
            ("x0", len(pix.x)),
            ("x1", len(pix.x)),
            ("y0", len(pix.y)),
            ("y1", len(pix.y)),
        ])
        self.out = out = Record([
            ("stb", 1),
            ("ack", 1),
            ("cnt", len(pix.x) + len(pix.y) + 16 - shift),
        ])

        ###

        y_good = Signal()
        x_good = Signal()
        self.comb += [
                y_good.eq((pix.y >= cfg.y0) & (pix.y < cfg.y1)),
                x_good.eq((pix.x >= cfg.x0) & (pix.x < cfg.x1)),
        ]
        done = Signal()
        self.sync += [
                If(pix.stb & x_good & y_good,
                    out.cnt.eq(out.cnt + Cat(pix.a, pix.b)[shift:]),
                    done.eq(1),
                ),
                If(done & pix.eop,
                    out.stb.eq(1),
                ),
                If(out.stb & out.ack,
                    out.stb.eq(0),
                    out.cnt.eq(0),
                    done.eq(0),
                ),
        ]

    def test(self, ret, x0=0, x1=0, y0=0, y1=0):
        yield self.cfg.x0.eq(x0)
        yield self.cfg.x1.eq(x1)
        yield self.cfg.y0.eq(y0)
        yield self.cfg.y1.eq(y1)
        assert not (yield self.out.stb)
        while not (yield self.out.stb):
            yield
        yield self.out.ack.eq(1)
        ret.append((yield self.out.cnt))
        yield
        yield self.out.ack.eq(0)
        yield
        assert not (yield self.out.stb)
        assert (yield self.out.cnt) == 0


class Grabber(Module):
    def __init__(self, n, width):
        self.submodules.parser = parser = Parser(width)
        self.roi = [ROI(parser.pix) for i in range(n)]
        self.submodules += self.roi


if __name__ == "__main__":
    d = Grabber(3, 12)
    nx, ny = 3, 4
    data0 = [[i*nx + j for j in range(nx)] for i in range(ny)]
    f = cameralink.Frame(data0)
    ret = []
    c = []
    run_simulation(d, [
        d.parser.test(f.gen_frame(), ret),
        d.roi[1].test(c, x1=1, y1=3),
        d.roi[2].test(c, x1=10, y1=10),
        ], vcd_name="grabber.vcd")
    assert c == [(0 + 3 + 6), (sum(range(nx*ny)))], c
    assert len(ret) == nx*ny
    for (x, y), (a, b, c) in ret:
        assert data0[y][x] == a, (x, y, a)

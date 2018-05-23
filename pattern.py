from migen import *
from migen.build.generic_platform import *
from migen.genlib.resetsync import AsyncResetSynchronizer
from microscope import *

from cameralink import Frame
from cl_phy import Deserializer


class CRG(Module):
    def __init__(self, platform):
        clk125 = platform.request("clk125_gtp")
        platform.add_period_constraint(clk125, 8.)
        clk125_div2 = Signal()
        self.clock_domains.cd_sys = ClockDomain("sys")
        self.specials += [
            Instance("IBUFDS_GTE2",
                i_CEB=0,
                i_I=clk125.p, i_IB=clk125.n,
                o_ODIV2=clk125_div2),
            Instance("BUFG",
                i_I=clk125_div2,
                o_O=self.cd_sys.clk),
        ]


class Serializer(Module):
    def __init__(self, pins):
        self.clock_domains.cd_par = ClockDomain("par")
        self.data = Signal(7*len(pins.sdo_p))

        pll_locked = Signal()
        pll_fb = Signal()
        pll_out = Signal(2)
        ser_clk = Signal()

        # system clock @62.5MHz
        self.specials += [
            Instance("PLLE2_BASE",
                p_CLKIN1_PERIOD=16.0,
                i_CLKIN1=ClockSignal(),

                i_CLKFBIN=pll_fb,
                o_CLKFBOUT=pll_fb,
                o_LOCKED=pll_locked,

                p_CLKFBOUT_MULT=2*7, p_DIVCLK_DIVIDE=1,

                p_CLKOUT0_DIVIDE=2, o_CLKOUT0=pll_out[0],
                p_CLKOUT1_DIVIDE=2*7, o_CLKOUT1=pll_out[1],
            ),
            Instance("BUFG", i_I=pll_out[0], o_O=ser_clk),
            Instance("BUFG", i_I=pll_out[1], o_O=self.cd_par.clk),
            AsyncResetSynchronizer(self.cd_par, ~pll_locked)
        ]
        self.submodules += add_probe_async("ser", "locked", pll_locked)

        for i in range(len(pins.sdo_p)):
            pdo = Signal(7)
            self.comb += pdo.eq(self.data[i*7:(i + 1)*7])
            sdo = Signal()
            self.specials += [
                Instance("OSERDESE2",
                    p_DATA_WIDTH=7,
                    p_TRISTATE_WIDTH=1,
                    p_DATA_RATE_OQ="SDR",
                    p_DATA_RATE_TQ="SDR",
                    p_SERDES_MODE="MASTER",
                    i_CLKDIV=ClockSignal("par"),
                    i_CLK=ser_clk, i_RST=ResetSignal("par"),
                    i_OCE=1,
                    i_D7=pdo[6], i_D6=pdo[5], i_D5=pdo[4],
                    i_D4=pdo[3], i_D3=pdo[2], i_D2=pdo[1], i_D1=pdo[0],
                    i_TCE=1,
                    i_T1=0, i_T2=0, i_T3=0, i_T4=0,
                    i_TBYTEIN=0, i_SHIFTIN1=0, i_SHIFTIN2=0,
                    o_OQ=sdo),
                Instance("OBUFDS",
                    i_I=sdo,
                    o_O=pins.sdo_p[i],
                    o_OB=pins.sdo_n[i])
            ]

class Top(Module):
    def __init__(self, platform):
        self.submodules += CRG(platform)

        serializer = Serializer(platform.request("camera_link_out"))
        self.submodules += serializer

        deserializer = Deserializer(platform.request("camera_link_in"))
        self.submodules += deserializer
        self.submodules += add_probe_async("grabber", "clk", deserializer.q_clk)

        w, h = 30, 20
        frame = Frame([list(range(i*w, (i + 1)*w)) for i in range(h)])
        data = [0b1100001 | (i << 7) for i in frame.gen_frame()]
        assert len(serializer.data) == 7 + 28

        mem = Memory(width=len(serializer.data), depth=len(data), init=data)
        memp = mem.get_port(clock_domain="par")
        self.sync.par += [
            memp.adr.eq(memp.adr + 1),
            If(memp.adr == len(data) - 1,
                memp.adr.eq(0)
            ),
            serializer.data.eq(memp.dat_r)
        ]
        self.specials += mem, memp
        self.submodules += add_probe_buffer("mem", "adr", memp.adr,
                                            clock_domain="par")

        self.submodules += Microscope(platform.request("serial"), 1/16e-9)


if __name__ == "__main__":
    from migen.build.platforms.sinara import kasli
    plat = kasli.Platform(hw_rev="v1.0")
    plat.add_extension([
        ("camera_link_in", 0,
            Subsignal("clk_p", Pins("eem0:d0_cc_p")),
            Subsignal("clk_n", Pins("eem0:d0_cc_n")),
            Subsignal("sdi_p", Pins("eem0:d4_p eem0:d3_p eem0:d2_p eem0:d1_p")),
            Subsignal("sdi_n", Pins("eem0:d4_n eem0:d3_n eem0:d2_n eem0:d1_n")),
            IOStandard("LVDS_25"),
            Misc("DIFF_TERM=TRUE")
        ),
        ("camera_link_out", 0,
            Subsignal("sdo_p", Pins(
                "eem1:d0_cc_p eem1:d4_p eem1:d3_p eem1:d2_p eem1:d1_p")),
            Subsignal("sdo_n", Pins(
                "eem1:d0_cc_n eem1:d4_n eem1:d3_n eem1:d2_n eem1:d1_n")),
            IOStandard("LVDS_25"),
        ),
    ])
    top = Top(plat)
    plat.build(top)

from migen import *
from migen.build.generic_platform import *
from migen.genlib.resetsync import AsyncResetSynchronizer
from microscope import *

from cameralink import Frame


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
        self.clock_domains.cd_por = ClockDomain(reset_less=True)
        por = Signal(reset=1)
        self.comb += [
            self.cd_por.clk.eq(self.cd_sys.clk),
            self.cd_sys.rst.eq(por),
        ]
        self.sync.por += por.eq(0)


class Serializer(Module):
    def __init__(self, pins, mul=6, div=1, n=7,
                 clock_domain="sys", clk_period=8.):
        # par (pixel clock): clk_period*div
        # ser (bit clock): clk_period*div/n

        self.clock_domains.cd_par = ClockDomain("par")
        self.data = Signal(n*len(pins.sdo_p))

        locked = Signal()
        pllout = Signal(6 + 1)
        ser_clk = Signal()

        self.specials += [
            Instance("PLLE2_ADV",
                p_CLKIN1_PERIOD=clk_period,
                i_CLKIN1=ClockSignal(clock_domain),
                i_RST=ResetSignal(clock_domain),
                p_DIVCLK_DIVIDE=div, i_CLKFBIN=self.cd_par.clk,
                p_CLKFBOUT_MULT=n*mul, o_CLKFBOUT=pllout[-1],
                p_CLKOUT0_DIVIDE=mul, o_CLKOUT0=pllout[0],
                i_CLKIN2=0, i_CLKINSEL=1,
                i_PWRDWN=0, o_LOCKED=locked,
                i_DADDR=0, i_DCLK=0, i_DEN=0, i_DI=0, i_DWE=0),
            Instance("BUFH", i_I=pllout[0], o_O=ser_clk),
            Instance("BUFH", i_I=pllout[-1], o_O=self.cd_par.clk),
            AsyncResetSynchronizer(self.cd_par, ~locked),
        ]

        for i in range(len(pins.sdo_p)):
            pdo = Signal(8)
            self.comb += pdo.eq(self.data[i*n:(i + 1)*n])
            sdo = Signal()
            self.specials += [
                    Instance("OSERDESE2",
                        p_DATA_WIDTH=n,
                        p_TRISTATE_WIDTH=1,
                        p_DATA_RATE_OQ="SDR",
                        p_DATA_RATE_TQ="SDR",
                        p_SERDES_MODE="MASTER",
                        i_CLKDIV=ClockSignal("par"),
                        i_CLK=ser_clk, i_RST=ResetSignal("par"),
                        i_OCE=1,
                        i_D8=pdo[7], i_D7=pdo[6], i_D6=pdo[5], i_D5=pdo[4],
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

        self.submodules += [
            add_probe_async("ser", "locked", locked),
        ]


class Top(Module):
    def __init__(self, platform):
        self.submodules += CRG(platform)

        serializer = Serializer(platform.request("camera_link_out"),
                clk_period=16., div=2)
        self.submodules += serializer

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
        self.submodules += [
            add_probe_buffer("mem", "adr", memp.adr, clock_domain="par")
        ]

        self.submodules += Microscope(platform.request("serial"), 1/16e-9)


if __name__ == "__main__":
    from migen.build.platforms.sinara import kasli
    plat = kasli.Platform(hw_rev="v1.1")
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

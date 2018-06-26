from migen import *
from migen.build.generic_platform import *
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


class Top(Module):
    def __init__(self, platform):
        self.submodules += Microscope(platform.request("serial"), 1/16e-9)

        self.submodules += CRG(platform)

        deserializer = Deserializer(platform.request("camera_link_in"))
        self.submodules += deserializer
        self.submodules += [
            add_probe_async("grabber", "q_clk", deserializer.q_clk),
            add_probe_buffer("grabber", "q", deserializer.q,
                             clock_domain="cl")
        ]


if __name__ == "__main__":
    from migen.build.platforms.sinara import kasli
    plat = kasli.Platform(hw_rev="v1.1")
    plat.add_extension([
        ("camera_link_in", 0,
            Subsignal("clk_p", Pins("eem6:d0_cc_p")),
            Subsignal("clk_n", Pins("eem6:d0_cc_n")),
            Subsignal("sdi_p", Pins("eem6:d4_p eem6:d3_p eem6:d2_p eem6:d1_p")),
            Subsignal("sdi_n", Pins("eem6:d4_n eem6:d3_n eem6:d2_n eem6:d1_n")),
            IOStandard("LVDS_25"),
            Misc("DIFF_TERM=TRUE")
        ),
    ])
    top = Top(plat)
    plat.build(top)

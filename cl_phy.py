from migen import *
from migen.genlib.resetsync import AsyncResetSynchronizer
from migen.build.platforms import kc705

from misoc.interconnect.csr import *

from microscope import *


# See:
# http://www.volkerschatz.com/hardware/clink.html

class Deserializer(Module, AutoCSR):
    def __init__(self, clk, data):
        self.phase_shift = CSR()
        self.phase_shift_done = CSRStatus(reset=1)

        self.q_clk = Signal(7)

        self.clock_domains.cd_cl = ClockDomain()
        self.clock_domains.cd_cl7x = ClockDomain()

        # # #

        clk_se = Signal()
        self.specials += Instance("IBUFDS",
            i_I=clk.p, i_IB=clk.n, o_O=clk_se)

        clk_se_iserdes = Signal()
        self.specials += [
            Instance("ISERDESE2",
                p_DATA_WIDTH=7, p_DATA_RATE="SDR",
                p_SERDES_MODE="MASTER", p_INTERFACE_TYPE="NETWORKING",
                p_NUM_CE=1,

                i_D=clk_se,
                o_O=clk_se_iserdes,
                i_CE1=1,
                i_CLKDIV=ClockSignal("cl"), i_RST=ResetSignal("cl"),
                i_CLK=ClockSignal("cl7x"), i_CLKB=~ClockSignal("cl7x"),
                o_Q7=self.q_clk[6],
                o_Q6=self.q_clk[5], o_Q5=self.q_clk[4],
                o_Q4=self.q_clk[3], o_Q3=self.q_clk[2],
                o_Q2=self.q_clk[1], o_Q1=self.q_clk[0]
            )
        ]

        # CL clock frequency 40-85MHz
        # A7-2 MMCM VCO frequency 600-1440MHz
        # A7-2 PLL  VCO frequency 800-1866MHz
        # with current MMCM settings, CL frequency limited to 40-~68MHz
        # TODO: switch to the PLL, whose VCO range better matches the CL
        # clock frequencies. Needs DRP for dynamic phase shift, see XAPP888.
        mmcm_fb = Signal()
        mmcm_locked = Signal()
        mmcm_ps_psdone = Signal()
        cl_clk = Signal()
        cl7x_clk = Signal()
        self.specials += [
            Instance("MMCME2_ADV",
                p_CLKIN1_PERIOD=18.0,
                i_CLKIN1=clk_se_iserdes,
                i_RST=0,
                i_CLKINSEL=1,  # yes, 1=CLKIN1 0=CLKIN2

                p_CLKFBOUT_MULT_F=21.0,
                p_DIVCLK_DIVIDE=4,  # XXX for KC705 test; set back to 1
                o_LOCKED=mmcm_locked,

                o_CLKFBOUT=mmcm_fb, i_CLKFBIN=mmcm_fb,

                p_CLKOUT0_USE_FINE_PS="TRUE",
                p_CLKOUT0_DIVIDE_F=21.0,
                o_CLKOUT0=cl_clk,

                p_CLKOUT1_USE_FINE_PS="TRUE",
                p_CLKOUT1_DIVIDE=3,
                o_CLKOUT1=cl7x_clk,

                i_PSCLK=ClockSignal(),
                i_PSEN=self.phase_shift.re,
                i_PSINCDEC=self.phase_shift.r,
                o_PSDONE=mmcm_ps_psdone,
            ),
            Instance("BUFG", i_I=cl_clk, o_O=self.cd_cl.clk),
            Instance("BUFG", i_I=cl7x_clk, o_O=self.cd_cl7x.clk),
            AsyncResetSynchronizer(self.cd_cl, ~mmcm_locked),
        ]
        self.sync += [
            If(self.phase_shift.re, self.phase_shift_done.status.eq(0)),
            If(mmcm_ps_psdone, self.phase_shift_done.status.eq(1))
        ]


class Test(Module):
    def __init__(self, platform):
        self.clock_domains.cd_sys = ClockDomain(reset_less=True)
        clk156 = platform.request("clk156")
        self.specials += Instance("IBUFGDS", i_I=clk156.p, i_IB=clk156.n, o_O=self.cd_sys.clk)

        self.submodules += Microscope(platform.request("serial"), 156e6)
        self.submodules.dut = Deserializer(platform.request("clk200"), None)
        self.submodules += add_probe_single("grabber", "clk", self.dut.q_clk)



def main():
    platform = kc705.Platform()
    top = Test(platform)
    platform.build(top, build_dir="grabber_test")


if __name__ == "__main__":
    main()
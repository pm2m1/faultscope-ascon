# FaultScope-Ascon Phase 15: PROVISIONAL Nexys 4 DDR Rev. C pin map.
# Selected from Digilent/digilent-xdc/Nexys-4-DDR-Master.xdc (not Nexys-4-Master.xdc).
# https://github.com/Digilent/digilent-xdc/blob/master/Nexys-4-DDR-Master.xdc
# Requires visual confirmation of the actual board revision before any programming.
# No guessed external input/output delay, reset recovery/removal, or CDC exception.

# 100 MHz onboard oscillator, CLK100MHZ, pin E3, bank 35.
set_property -dict { PACKAGE_PIN E3 IOSTANDARD LVCMOS33 } [get_ports {clk}]
create_clock -name board_clk_100mhz -period 10.000 -waveform {0.000 5.000} [get_ports {clk}]

# CPU_RESETN: physical reset button drives low on press; FPGA rst_n is active low.
set_property -dict { PACKAGE_PIN C12 IOSTANDARD LVCMOS33 } [get_ports {rst_n}]

# FT2232 UART naming in Digilent master is from bridge perspective:
# UART_TXD_IN (C4) is FPGA receive input; UART_RXD_OUT (D4) is FPGA transmit output.
set_property -dict { PACKAGE_PIN C4 IOSTANDARD LVCMOS33 } [get_ports {uart_rx_i}]
set_property -dict { PACKAGE_PIN D4 IOSTANDARD LVCMOS33 } [get_ports {uart_tx_o}]

# Two board user LEDs, LED[0] / LED[1].
set_property -dict { PACKAGE_PIN H17 IOSTANDARD LVCMOS33 } [get_ports {led_busy_o}]
set_property -dict { PACKAGE_PIN K15 IOSTANDARD LVCMOS33 } [get_ports {led_alarm_o}]

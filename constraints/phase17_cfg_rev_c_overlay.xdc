# Phase 17: PROVISIONAL Nexys 4 DDR Rev. C CONFIG bank experiment.
# Digilent Nexys 4 DDR schematic: CFG_BVS_0 wired to VCC3V3; verify actual PCB before programming.
# https://digilent.com/reference/_media/nexys4-ddr/nexys_4_ddr_sch.pdf
# UG912/UG899: applies only to the documented 3.3 V configuration bank.
# No changes to I/O pins, clocks, timing exceptions or external delays.
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]

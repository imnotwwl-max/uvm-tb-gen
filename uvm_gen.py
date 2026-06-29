#!/usr/bin/env python3
"""
UVM Testbench Generator
Generates a complete UVM testbench skeleton from user inputs.
Supports generic agents and Cadence AXI Master VIP (svt_axi_master_agent).
"""

import os
import sys

AGENT_TYPES = {
    "1": "generic",
    "2": "axi_vip_master",
}

AGENT_TYPE_LABELS = {
    "generic":        "Generic (custom driver/monitor)",
    "axi_vip_master": "Cadence AXI Master VIP (svt_axi_master_agent)",
}


def prompt(msg, default=None):
    if default is not None:
        ans = input(f"{msg} [{default}]: ").strip()
        return ans if ans else default
    while True:
        ans = input(f"{msg}: ").strip()
        if ans:
            return ans
        print("  (cannot be empty, please try again)")


def prompt_int(msg, min_val=1, max_val=16):
    while True:
        try:
            val = int(input(f"{msg} ({min_val}-{max_val}): ").strip())
            if min_val <= val <= max_val:
                return val
            print(f"  Please enter a number between {min_val} and {max_val}.")
        except ValueError:
            print("  Please enter a valid integer.")


def prompt_agent_type(agent_name):
    print(f"\n  Agent type for '{agent_name}':")
    for k, v in AGENT_TYPES.items():
        print(f"    [{k}] {AGENT_TYPE_LABELS[v]}")
    while True:
        ans = input("  Choice [1]: ").strip() or "1"
        if ans in AGENT_TYPES:
            return AGENT_TYPES[ans]
        print("  Please enter 1 or 2.")


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    print(f"  [GEN] {path}")


# ---------------------------------------------------------------------------
# Generic agent templates
# ---------------------------------------------------------------------------

def gen_interface(agent_name):
    a = agent_name
    return f"""\
// {a}_if.sv — virtual interface for {a}
interface {a}_if (input logic clk, input logic rst_n);

  logic       valid;
  logic [7:0] data;
  logic       ready;

  clocking driver_cb @(posedge clk);
    default input #1 output #1;
    output valid;
    output data;
    input  ready;
  endclocking

  clocking monitor_cb @(posedge clk);
    default input #1;
    input valid;
    input data;
    input ready;
  endclocking

  modport driver_mp  (clocking driver_cb,  input rst_n);
  modport monitor_mp (clocking monitor_cb, input rst_n);

endinterface : {a}_if
"""


def gen_seq_item(agent_name):
    a = agent_name
    return f"""\
// {a}_seq_item.sv
class {a}_seq_item extends uvm_sequence_item;

  `uvm_object_utils_begin({a}_seq_item)
    `uvm_field_int(data, UVM_ALL_ON)
  `uvm_object_utils_end

  rand logic [7:0] data;

  function new(string name = "{a}_seq_item");
    super.new(name);
  endfunction

endclass : {a}_seq_item
"""


def gen_driver(agent_name):
    a = agent_name
    return f"""\
// {a}_driver.sv
class {a}_driver extends uvm_driver #({a}_seq_item);

  `uvm_component_utils({a}_driver)

  virtual {a}_if vif;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    if (!uvm_config_db #(virtual {a}_if)::get(this, "", "vif", vif))
      `uvm_fatal("NOVIF", $sformatf("%s: virtual interface not found", get_full_name()))
  endfunction

  task run_phase(uvm_phase phase);
    {a}_seq_item req;
    @(posedge vif.clk iff vif.rst_n);
    forever begin
      seq_item_port.get_next_item(req);
      drive_item(req);
      seq_item_port.item_done();
    end
  endtask

  task drive_item({a}_seq_item req);
    @(vif.driver_cb);
    vif.driver_cb.valid <= 1'b1;
    vif.driver_cb.data  <= req.data;
    @(vif.driver_cb iff vif.driver_cb.ready);
    vif.driver_cb.valid <= 1'b0;
  endtask

endclass : {a}_driver
"""


def gen_monitor(agent_name):
    a = agent_name
    return f"""\
// {a}_monitor.sv
class {a}_monitor extends uvm_monitor;

  `uvm_component_utils({a}_monitor)

  virtual {a}_if vif;
  uvm_analysis_port #({a}_seq_item) ap;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    ap = new("ap", this);
    if (!uvm_config_db #(virtual {a}_if)::get(this, "", "vif", vif))
      `uvm_fatal("NOVIF", $sformatf("%s: virtual interface not found", get_full_name()))
  endfunction

  task run_phase(uvm_phase phase);
    {a}_seq_item trans;
    @(posedge vif.clk iff vif.rst_n);
    forever begin
      @(vif.monitor_cb iff vif.monitor_cb.valid && vif.monitor_cb.ready);
      trans = {a}_seq_item::type_id::create("trans");
      trans.data = vif.monitor_cb.data;
      ap.write(trans);
    end
  endtask

endclass : {a}_monitor
"""


def gen_agent(agent_name):
    a = agent_name
    return f"""\
// {a}_agent.sv
class {a}_agent extends uvm_agent;

  `uvm_component_utils({a}_agent)

  {a}_driver  drv;
  {a}_monitor mon;
  uvm_sequencer #({a}_seq_item) seqr;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    mon  = {a}_monitor::type_id::create("mon",  this);
    if (is_active == UVM_ACTIVE) begin
      seqr = uvm_sequencer #({a}_seq_item)::type_id::create("seqr", this);
      drv  = {a}_driver::type_id::create("drv",  this);
    end
  endfunction

  function void connect_phase(uvm_phase phase);
    if (is_active == UVM_ACTIVE)
      drv.seq_item_port.connect(seqr.seq_item_export);
  endfunction

endclass : {a}_agent
"""


# ---------------------------------------------------------------------------
# Cadence AXI Master VIP templates
# ---------------------------------------------------------------------------

def gen_axi_cfg(agent_name):
    a = agent_name
    return f"""\
// {a}_axi_cfg.sv — Cadence AXI VIP port configuration wrapper for {a}
class {a}_axi_cfg extends uvm_object;

  `uvm_object_utils({a}_axi_cfg)

  svt_axi_port_configuration port_cfg;

  function new(string name = "{a}_axi_cfg");
    super.new(name);
    port_cfg = new("port_cfg");
    // AXI4 Master, 32-bit address, 32-bit data — adjust as needed
    port_cfg.axi_interface_type  = svt_axi_port_configuration::AXI4;
    port_cfg.port_kind           = svt_axi_port_configuration::MASTER;
    port_cfg.addr_width          = 32;
    port_cfg.data_width          = 32;
    port_cfg.id_width            = 4;
    port_cfg.is_active           = 1;
  endfunction

endclass : {a}_axi_cfg
"""


def gen_axi_seq_item(agent_name):
    a = agent_name
    return f"""\
// {a}_axi_seq_item.sv — thin wrapper / alias for Cadence AXI VIP transaction
// The VIP uses svt_axi_master_transaction natively; this typedef makes it
// easy to reference in virtual sequencer and scoreboards.
typedef svt_axi_master_transaction {a}_axi_seq_item;
"""


def gen_axi_seq(agent_name):
    a = agent_name
    return f"""\
// {a}_axi_seq.sv — example AXI master sequences
class {a}_axi_write_seq extends svt_axi_master_base_sequence;

  `uvm_object_utils({a}_axi_write_seq)

  rand bit [31:0] addr;
  rand bit [31:0] data;

  function new(string name = "{a}_axi_write_seq");
    super.new(name);
  endfunction

  task body();
    svt_axi_master_transaction req;
    `uvm_create(req)
    req.xact_type    = svt_axi_transaction::WRITE;
    req.addr         = addr;
    req.data[0]      = data;
    req.burst_length = 1;
    req.burst_type   = svt_axi_transaction::INCR;
    req.burst_size   = svt_axi_transaction::BURST_SIZE_32BIT;
    `uvm_send(req)
    get_response(rsp);
  endtask

endclass : {a}_axi_write_seq


class {a}_axi_read_seq extends svt_axi_master_base_sequence;

  `uvm_object_utils({a}_axi_read_seq)

  rand bit [31:0] addr;

  function new(string name = "{a}_axi_read_seq");
    super.new(name);
  endfunction

  task body();
    svt_axi_master_transaction req;
    `uvm_create(req)
    req.xact_type    = svt_axi_transaction::READ;
    req.addr         = addr;
    req.burst_length = 1;
    req.burst_type   = svt_axi_transaction::INCR;
    req.burst_size   = svt_axi_transaction::BURST_SIZE_32BIT;
    `uvm_send(req)
    get_response(rsp);
  endtask

endclass : {a}_axi_read_seq
"""


def gen_axi_agent_wrapper(agent_name):
    a = agent_name
    return f"""\
// {a}_agent.sv — thin wrapper around svt_axi_master_agent
// Exposes the same interface as a generic agent so the env can treat
// all agents uniformly: .seqr and .mon.ap
class {a}_agent extends uvm_component;

  `uvm_component_utils({a}_agent)

  svt_axi_master_agent          vip_agent;
  {a}_axi_cfg                   cfg;

  // Forwarded handle — virtual sequencer binds to this
  uvm_sequencer #(svt_axi_master_transaction) seqr;

  // Forwarded analysis port — scoreboard connects to this
  uvm_analysis_port #(svt_axi_master_transaction) ap;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    cfg       = {a}_axi_cfg::type_id::create("cfg");
    ap        = new("ap", this);
    uvm_config_db #(svt_axi_port_configuration)::set(
      this, "vip_agent", "cfg", cfg.port_cfg);
    vip_agent = svt_axi_master_agent::type_id::create("vip_agent", this);
  endfunction

  function void connect_phase(uvm_phase phase);
    seqr = vip_agent.sequencer;
    // Forward observed transactions from VIP monitor to our ap
    vip_agent.monitor.item_observed_port.connect(ap);
  endfunction

endclass : {a}_agent
"""


# ---------------------------------------------------------------------------
# Scoreboard (works for both generic and AXI VIP — parameterised by item type)
# ---------------------------------------------------------------------------

def gen_scoreboard(sb_name, agent_name, agent_type):
    s = sb_name
    a = agent_name
    item = "svt_axi_master_transaction" if agent_type == "axi_vip_master" else f"{a}_seq_item"
    return f"""\
// {s}.sv — scoreboard connected to {a} monitor
class {s} extends uvm_scoreboard;

  `uvm_component_utils({s})

  uvm_analysis_imp #({item}, {s}) analysis_export;

  int unsigned pass_count;
  int unsigned fail_count;

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
    analysis_export = new("analysis_export", this);
    pass_count = 0;
    fail_count = 0;
  endfunction

  function void write({item} trans);
    // TODO: implement checking logic
    `uvm_info(get_type_name(),
      $sformatf("Received transaction"), UVM_MEDIUM)
    pass_count++;
  endfunction

  function void report_phase(uvm_phase phase);
    `uvm_info(get_type_name(),
      $sformatf("SCOREBOARD REPORT — PASS: %0d  FAIL: %0d",
                pass_count, fail_count), UVM_NONE)
    if (fail_count > 0)
      `uvm_error(get_type_name(), "Test FAILED")
    else
      `uvm_info(get_type_name(), "Test PASSED", UVM_NONE)
  endfunction

endclass : {s}
"""


# ---------------------------------------------------------------------------
# Top-level shared templates
# ---------------------------------------------------------------------------

def gen_virtual_sequencer(proj, agents):
    p = proj
    seqr_decls = []
    for a, t in agents:
        if t == "axi_vip_master":
            seqr_decls.append(
                f"  uvm_sequencer #(svt_axi_master_transaction) {a}_seqr;")
        else:
            seqr_decls.append(
                f"  uvm_sequencer #({a}_seq_item) {a}_seqr;")
    return f"""\
// {p}_virtual_sequencer.sv
class {p}_virtual_sequencer extends uvm_sequencer;

  `uvm_component_utils({p}_virtual_sequencer)

{chr(10).join(seqr_decls)}

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

endclass : {p}_virtual_sequencer
"""


def gen_virtual_sequence(proj, agents):
    p = proj
    return f"""\
// {p}_virtual_sequence.sv
class {p}_base_virtual_seq extends uvm_sequence;

  `uvm_object_utils({p}_base_virtual_seq)
  `uvm_declare_p_sequencer({p}_virtual_sequencer)

  function new(string name = "{p}_base_virtual_seq");
    super.new(name);
  endfunction

  task body();
    // Override in derived virtual sequences
  endtask

endclass : {p}_base_virtual_seq
"""


def gen_env(proj, agents, sb_pairs):
    p = proj
    agent_decls    = "\n".join(f"  {a}_agent {a};"    for a, _ in agents)
    sb_decls       = "\n".join(f"  {s} {s}_inst;"     for s, _, __ in sb_pairs)
    vseqr_decl     = f"  {p}_virtual_sequencer vseqr;"

    agent_creates  = "\n".join(
        f'    {a} = {a}_agent::type_id::create("{a}", this);' for a, _ in agents)
    sb_creates     = "\n".join(
        f'    {s}_inst = {s}::type_id::create("{s}_inst", this);' for s, _, __ in sb_pairs)
    vseqr_create   = f'    vseqr = {p}_virtual_sequencer::type_id::create("vseqr", this);'

    vseqr_connects = "\n".join(
        f"    vseqr.{a}_seqr = {a}.seqr;" for a, _ in agents)
    sb_connects    = "\n".join(
        f"    {a}.ap.connect({s}_inst.analysis_export);" for s, a, _ in sb_pairs)

    return f"""\
// {p}_env.sv
class {p}_env extends uvm_env;

  `uvm_component_utils({p}_env)

{agent_decls}
{sb_decls}
{vseqr_decl}

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
{agent_creates}
{sb_creates}
{vseqr_create}
  endfunction

  function void connect_phase(uvm_phase phase);
{vseqr_connects}
{sb_connects}
  endfunction

endclass : {p}_env
"""


def gen_base_test(proj, agents):
    p = proj
    generic_agents = [(a, t) for a, t in agents if t == "generic"]

    vif_decls = "\n".join(f"  virtual {a}_if {a}_vif;" for a, _ in generic_agents)
    vif_gets  = "\n".join(
        f'    if (!uvm_config_db #(virtual {a}_if)::get(this, "", "{a}_vif", {a}_vif))\n'
        f'      `uvm_fatal("NOVIF", "{a}_vif not found in config_db")'
        for a, _ in generic_agents)
    vif_sets  = "\n".join(
        f'    uvm_config_db #(virtual {a}_if)::set(this, "{p}_env.{a}.*", "vif", {a}_vif);'
        for a, _ in generic_agents)

    return f"""\
// {p}_base_test.sv
class {p}_base_test extends uvm_test;

  `uvm_component_utils({p}_base_test)

  {p}_env env;
{vif_decls}

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

  function void build_phase(uvm_phase phase);
    super.build_phase(phase);
{vif_gets}
{vif_sets}
    env = {p}_env::type_id::create("env", this);
  endfunction

  task run_phase(uvm_phase phase);
    phase.raise_objection(this);
    // Override in derived tests — run virtual sequences here
    #100;
    phase.drop_objection(this);
  endtask

endclass : {p}_base_test
"""


def gen_tb_top(proj, agents):
    p = proj
    generic_agents = [(a, t) for a, t in agents if t == "generic"]
    axi_agents     = [(a, t) for a, t in agents if t == "axi_vip_master"]

    iface_insts = "\n".join(
        f"  {a}_if {a}_if_inst (.clk(clk), .rst_n(rst_n));"
        for a, _ in generic_agents)
    axi_iface_insts = "\n".join(
        f"  svt_axi_if {a}_axi_if ();" for a, _ in axi_agents)

    generic_cfg_sets = "\n".join(
        f'    uvm_config_db #(virtual {a}_if)::set(null, "uvm_test_top", "{a}_vif", {a}_if_inst);'
        for a, _ in generic_agents)
    axi_cfg_sets = "\n".join(
        f'    uvm_config_db #(virtual svt_axi_if)::set(null, "uvm_test_top.env.{a}.vip_agent", "vif", {a}_axi_if);'
        for a, _ in axi_agents)

    axi_comment = (
        "\n  // Connect AXI VIP interfaces to DUT signals here\n"
        + "\n".join(
            f"  // assign {a}_axi_if.awaddr = dut.awaddr; // etc."
            for a, _ in axi_agents)
        if axi_agents else ""
    )

    return f"""\
// {p}_tb_top.sv
`timescale 1ns/1ps

module {p}_tb_top;

  import uvm_pkg::*;
  `include "uvm_macros.svh"
  `include "{p}_pkg.sv"

  logic clk;
  logic rst_n;

  // Clock generation — 100 MHz
  initial clk = 0;
  always #5 clk = ~clk;

  // Reset
  initial begin
    rst_n = 0;
    repeat (5) @(posedge clk);
    rst_n = 1;
  end

  // Generic virtual interfaces
{iface_insts}

  // Cadence AXI VIP interfaces
{axi_iface_insts}
{axi_comment}

  // DUT placeholder
  // {p}_dut dut ( .clk(clk), .rst_n(rst_n), ... );

  initial begin
{generic_cfg_sets}
{axi_cfg_sets}
    run_test();
  end

endmodule : {p}_tb_top
"""


def gen_pkg(proj, agents, sb_pairs):
    p = proj
    has_axi = any(t == "axi_vip_master" for _, t in agents)

    axi_import = (
        "\n  // Cadence AXI VIP packages\n"
        "  import svt_uvm_pkg::*;\n"
        "  import svt_axi_uvm_pkg::*;\n"
        '  `include "svt_axi_if.svi"\n'
        if has_axi else ""
    )

    agent_includes = []
    for a, t in agents:
        if t == "axi_vip_master":
            agent_includes += [
                f'  `include "{a}_axi_cfg.sv"',
                f'  `include "{a}_axi_seq_item.sv"',
                f'  `include "{a}_axi_seq.sv"',
                f'  `include "{a}_agent.sv"',
            ]
        else:
            agent_includes += [
                f'  `include "{a}_seq_item.sv"',
                f'  `include "{a}_driver.sv"',
                f'  `include "{a}_monitor.sv"',
                f'  `include "{a}_agent.sv"',
            ]
    sb_includes = [f'  `include "{s}.sv"' for s, _, __ in sb_pairs]

    return f"""\
// {p}_pkg.sv
package {p}_pkg;

  import uvm_pkg::*;
  `include "uvm_macros.svh"
{axi_import}
  // Agent components
{chr(10).join(agent_includes)}

  // Scoreboards
{chr(10).join(sb_includes)}

  // Environment
  `include "{p}_virtual_sequencer.sv"
  `include "{p}_virtual_sequence.sv"
  `include "{p}_env.sv"

  // Tests
  `include "{p}_base_test.sv"

endpackage : {p}_pkg
"""


def gen_filelist(proj, agents, sb_pairs, tb_dir):
    has_axi = any(t == "axi_vip_master" for _, t in agents)
    lines = ["// Auto-generated filelist"]
    if has_axi:
        lines += [
            "",
            "// Cadence AXI VIP — set $CDS_VIP_ROOT to your VIP install path",
            "-y $CDS_VIP_ROOT/svt/svt_axi/latest/svt_axi_uvm",
            "+incdir+$CDS_VIP_ROOT/svt/svt_axi/latest/svt_axi_uvm/include",
        ]
    lines += ["", f"+incdir+{tb_dir}", "", "// Interfaces"]
    for a, t in agents:
        if t == "generic":
            lines.append(f"{tb_dir}/{a}_if.sv")
    lines += ["", "// Package (includes all classes)"]
    lines.append(f"{tb_dir}/{proj}_pkg.sv")
    lines += ["", "// Testbench top"]
    lines.append(f"{tb_dir}/{proj}_tb_top.sv")
    return "\n".join(lines) + "\n"


def gen_readme(proj, agents, sb_pairs):
    p = proj
    has_axi = any(t == "axi_vip_master" for _, t in agents)

    arch_agents = "\n".join(
        f"    ├── {a}_agent ({'Cadence AXI Master VIP' if t == 'axi_vip_master' else 'generic'})"
        for a, t in agents)
    arch_sbs = "\n".join(
        f"    ├── {s} (scoreboard ← {a})" for s, a, _ in sb_pairs)

    iface_rows = "\n".join(
        f"| `{a}_if.sv` | Virtual interface with clocking blocks for `{a}` |"
        for a, t in agents if t == "generic")

    agent_rows = ""
    for a, t in agents:
        if t == "axi_vip_master":
            agent_rows += (
                f"| `{a}_axi_cfg.sv` | Cadence AXI VIP port configuration (addr/data width, master mode) |\n"
                f"| `{a}_axi_seq_item.sv` | Typedef alias for `svt_axi_master_transaction` |\n"
                f"| `{a}_axi_seq.sv` | Example write/read sequences using Cadence VIP |\n"
                f"| `{a}_agent.sv` | Wrapper around `svt_axi_master_agent`; exposes `.seqr` and `.ap` |\n"
            )
        else:
            agent_rows += (
                f"| `{a}_seq_item.sv` | Randomisable transaction |\n"
                f"| `{a}_driver.sv` | Drives DUT signals via clocking block |\n"
                f"| `{a}_monitor.sv` | Observes bus; broadcasts via `analysis_port` |\n"
                f"| `{a}_agent.sv` | Bundles driver + monitor + sequencer |\n"
            )

    sb_rows = "\n".join(
        f"| `{s}.sv` | Scoreboard connected to `{a}` monitor; reports pass/fail |"
        for s, a, _ in sb_pairs)

    axi_note = (
        "\n> **Cadence AXI VIP requirement:**  \n"
        "> Set `$CDS_VIP_ROOT` to your Cadence VIP installation path before compiling.\n"
        if has_axi else ""
    )

    return f"""\
# {p} UVM Testbench

Auto-generated by `uvm_gen.py`.
{axi_note}
## Architecture

```
{p}_tb_top
└── {p}_env
    ├── {p}_virtual_sequencer
{arch_agents}
{arch_sbs}
```

## File descriptions

### Interfaces
| File | Description |
|------|-------------|
{iface_rows}

### Agent components
| File | Description |
|------|-------------|
{agent_rows}
### Scoreboards
| File | Description |
|------|-------------|
{sb_rows}

### Top-level
| File | Description |
|------|-------------|
| `{p}_virtual_sequencer.sv` | Holds handles to all agent sequencers |
| `{p}_virtual_sequence.sv` | Base virtual sequence — override `body()` in derived sequences |
| `{p}_env.sv` | Creates and connects all agents, scoreboards, and virtual sequencer |
| `{p}_base_test.sv` | Passes virtual interfaces via `uvm_config_db`; instantiates env |
| `{p}_tb_top.sv` | Top module; generates clock/reset and calls `run_test()` |
| `{p}_pkg.sv` | Package that `` `include ``s all testbench classes |
| `{p}.f` | Filelist for VCS / Xcelium |

## Compile & run (VCS example)

```bash
vcs -sverilog -f {p}.f -ntb_opts uvm-1.2 +UVM_TESTNAME={p}_base_test
./simv +UVM_VERBOSITY=UVM_MEDIUM
```
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  UVM Testbench Generator")
    print("=" * 60)
    print()

    proj        = prompt("Project name (e.g. my_proj)")
    n_agents    = prompt_int("Number of agents", 1, 16)
    n_scoreboards = prompt_int("Number of scoreboards", 1, 16)

    agent_names = [f"agent{i}" for i in range(n_agents)]
    sb_names    = [f"sb{i}" for i in range(n_scoreboards)]

    # Ask agent type per agent
    print()
    agent_types = []
    for a in agent_names:
        t = prompt_agent_type(a)
        agent_types.append(t)
    agents = list(zip(agent_names, agent_types))

    if n_scoreboards != n_agents:
        print(f"\n  Note: {n_agents} agent(s), {n_scoreboards} scoreboard(s).")
        print("  Scoreboards paired in order; extras connect to agent0.\n")

    out_dir = prompt("\nOutput directory", f"./{proj}_tb")
    tb_dir  = os.path.abspath(out_dir)

    print()
    print(f"Generating UVM testbench for project '{proj}' ...")
    for a, t in agents:
        print(f"  {a:12s} → {AGENT_TYPE_LABELS[t]}")
    print(f"  Scoreboards: {n_scoreboards}")
    print(f"  Output dir : {tb_dir}")
    print()

    n_pairs      = min(n_agents, n_scoreboards)
    sb_pairs     = [(sb_names[i], agent_names[i], agent_types[i]) for i in range(n_pairs)]
    for i in range(n_pairs, n_scoreboards):
        sb_pairs.append((sb_names[i], agent_names[0], agent_types[0]))

    def out(filename, content):
        write_file(os.path.join(tb_dir, filename), content)

    # Interfaces & agent files
    for a, t in agents:
        if t == "generic":
            out(f"{a}_if.sv",       gen_interface(a))
            out(f"{a}_seq_item.sv", gen_seq_item(a))
            out(f"{a}_driver.sv",   gen_driver(a))
            out(f"{a}_monitor.sv",  gen_monitor(a))
            out(f"{a}_agent.sv",    gen_agent(a))
        elif t == "axi_vip_master":
            out(f"{a}_axi_cfg.sv",      gen_axi_cfg(a))
            out(f"{a}_axi_seq_item.sv", gen_axi_seq_item(a))
            out(f"{a}_axi_seq.sv",      gen_axi_seq(a))
            out(f"{a}_agent.sv",        gen_axi_agent_wrapper(a))

    # Scoreboards
    for s, a, t in sb_pairs:
        out(f"{s}.sv", gen_scoreboard(s, a, t))

    # Shared top-level
    out(f"{proj}_virtual_sequencer.sv", gen_virtual_sequencer(proj, agents))
    out(f"{proj}_virtual_sequence.sv",  gen_virtual_sequence(proj, agents))
    out(f"{proj}_env.sv",               gen_env(proj, agents, sb_pairs))
    out(f"{proj}_base_test.sv",         gen_base_test(proj, agents))
    out(f"{proj}_tb_top.sv",            gen_tb_top(proj, agents))
    out(f"{proj}_pkg.sv",               gen_pkg(proj, agents, sb_pairs))
    out(f"{proj}.f",                    gen_filelist(proj, agents, sb_pairs, tb_dir))
    out("README.md",                    gen_readme(proj, agents, sb_pairs))

    print()
    print("Done! Generated files:")
    print(f"  {tb_dir}/")
    for f in sorted(os.listdir(tb_dir)):
        print(f"    {f}")
    print()
    print("To compile with VCS (example):")
    print(f"  vcs -sverilog -f {tb_dir}/{proj}.f -ntb_opts uvm-1.2 +UVM_TESTNAME={proj}_base_test")


if __name__ == "__main__":
    main()

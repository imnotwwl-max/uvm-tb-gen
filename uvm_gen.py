#!/usr/bin/env python3
"""
UVM Testbench Generator
Generates a complete UVM testbench skeleton from user inputs.
"""

import os
import sys


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


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    print(f"  [GEN] {path}")


# ---------------------------------------------------------------------------
# Template generators
# ---------------------------------------------------------------------------

def gen_interface(proj, agent_name):
    p = proj.upper()
    a = agent_name
    A = a.upper()
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


def gen_seq_item(proj, agent_name):
    p = proj
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


def gen_driver(proj, agent_name):
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


def gen_monitor(proj, agent_name):
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


def gen_agent(proj, agent_name):
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


def gen_scoreboard(proj, sb_name, agent_name):
    s = sb_name
    a = agent_name
    return f"""\
// {s}.sv — scoreboard connected to {a}_monitor
class {s} extends uvm_scoreboard;

  `uvm_component_utils({s})

  uvm_analysis_imp #({a}_seq_item, {s}) analysis_export;

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

  function void write({a}_seq_item trans);
    // TODO: implement checking logic
    `uvm_info(get_type_name(),
      $sformatf("Received: data=0x%0h", trans.data), UVM_MEDIUM)
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


def gen_virtual_sequencer(proj, agent_names):
    p = proj
    seqr_decls = "\n".join(
        f"  uvm_sequencer #({a}_seq_item) {a}_seqr;" for a in agent_names
    )
    return f"""\
// {p}_virtual_sequencer.sv
class {p}_virtual_sequencer extends uvm_sequencer;

  `uvm_component_utils({p}_virtual_sequencer)

{seqr_decls}

  function new(string name, uvm_component parent);
    super.new(name, parent);
  endfunction

endclass : {p}_virtual_sequencer
"""


def gen_virtual_sequence(proj, agent_names):
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


def gen_env(proj, agent_names, sb_pairs):
    p = proj
    agent_decls = "\n".join(f"  {a}_agent {a};" for a in agent_names)
    sb_decls = "\n".join(f"  {s} {s}_inst;" for s, _ in sb_pairs)
    vseqr_decl = f"  {p}_virtual_sequencer vseqr;"

    agent_creates = "\n".join(
        f'    {a} = {a}_agent::type_id::create("{a}", this);' for a in agent_names
    )
    sb_creates = "\n".join(
        f'    {s}_inst = {s}::type_id::create("{s}_inst", this);' for s, _ in sb_pairs
    )
    vseqr_create = f'    vseqr = {p}_virtual_sequencer::type_id::create("vseqr", this);'

    vseqr_connects = "\n".join(
        f"    vseqr.{a}_seqr = {a}.seqr;" for a in agent_names
    )
    sb_connects = "\n".join(
        f"    {a}.mon.ap.connect({s}_inst.analysis_export);" for s, a in sb_pairs
    )

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


def gen_base_test(proj, agent_names):
    p = proj
    vif_sets = "\n".join(
        f'    uvm_config_db #(virtual {a}_if)::set(this, "{p}_env.{a}.*", "vif", {a}_vif);'
        for a in agent_names
    )
    vif_ports = "\n".join(
        f"  virtual {a}_if {a}_vif;" for a in agent_names
    )
    vif_gets = "\n".join(
        f'    if (!uvm_config_db #(virtual {a}_if)::get(this, "", "{a}_vif", {a}_vif))\n'
        f'      `uvm_fatal("NOVIF", "{a}_vif not found in config_db")'
        for a in agent_names
    )

    return f"""\
// {p}_base_test.sv
class {p}_base_test extends uvm_test;

  `uvm_component_utils({p}_base_test)

  {p}_env env;
{vif_ports}

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


def gen_tb_top(proj, agent_names):
    p = proj
    iface_insts = "\n".join(
        f"  {a}_if {a}_if_inst (.clk(clk), .rst_n(rst_n));" for a in agent_names
    )
    config_sets = "\n".join(
        f'    uvm_config_db #(virtual {a}_if)::set(null, "uvm_test_top", "{a}_vif", {a}_if_inst);'
        for a in agent_names
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

  // Interface instances
{iface_insts}

  // DUT placeholder — instantiate your DUT here
  // {p}_dut dut (
  //   .clk   (clk),
  //   .rst_n (rst_n),
  //   ...
  // );

  initial begin
    // Pass virtual interfaces to config_db
{config_sets}
    run_test();
  end

endmodule : {p}_tb_top
"""


def gen_pkg(proj, agent_names, sb_pairs):
    p = proj
    agent_includes = []
    for a in agent_names:
        agent_includes += [
            f'  `include "{a}_seq_item.sv"',
            f'  `include "{a}_driver.sv"',
            f'  `include "{a}_monitor.sv"',
            f'  `include "{a}_agent.sv"',
        ]
    sb_includes = [f'  `include "{s}.sv"' for s, _ in sb_pairs]
    agent_block = "\n".join(agent_includes)
    sb_block = "\n".join(sb_includes)

    return f"""\
// {p}_pkg.sv — package that collects all testbench classes
package {p}_pkg;

  import uvm_pkg::*;
  `include "uvm_macros.svh"

  // Agent components
{agent_block}

  // Scoreboards
{sb_block}

  // Environment
  `include "{p}_virtual_sequencer.sv"
  `include "{p}_virtual_sequence.sv"
  `include "{p}_env.sv"

  // Tests
  `include "{p}_base_test.sv"

endpackage : {p}_pkg
"""


def gen_filelist(proj, agent_names, sb_pairs, tb_dir):
    lines = ["// Auto-generated filelist"]
    lines.append(f"+incdir+{tb_dir}")
    lines.append("")
    lines.append("// Interfaces")
    for a in agent_names:
        lines.append(f"{tb_dir}/{a}_if.sv")
    lines.append("")
    lines.append("// Package (includes all classes)")
    lines.append(f"{tb_dir}/{proj}_pkg.sv")
    lines.append("")
    lines.append("// Testbench top")
    lines.append(f"{tb_dir}/{proj}_tb_top.sv")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  UVM Testbench Generator")
    print("=" * 60)
    print()

    proj = prompt("Project name (e.g. my_proj)")
    n_agents = prompt_int("Number of agents", 1, 16)
    n_scoreboards = prompt_int("Number of scoreboards", 1, 16)

    if n_scoreboards != n_agents:
        print(f"\n  Note: {n_agents} agent(s), {n_scoreboards} scoreboard(s).")
        print("  Each scoreboard will be paired with an agent in order.")
        print("  Extra agents/scoreboards will not be connected.\n")

    out_dir = prompt("Output directory", f"./{proj}_tb")
    tb_dir = os.path.abspath(out_dir)

    print()
    print(f"Generating UVM testbench for project '{proj}' ...")
    print(f"  Agents     : {n_agents}  (agent0 .. agent{n_agents-1})")
    print(f"  Scoreboards: {n_scoreboards}  (sb0 .. sb{n_scoreboards-1})")
    print(f"  Output dir : {tb_dir}")
    print()

    agent_names = [f"agent{i}" for i in range(n_agents)]
    sb_names = [f"sb{i}" for i in range(n_scoreboards)]

    # Pair each scoreboard with one agent (up to min count)
    n_pairs = min(n_agents, n_scoreboards)
    sb_pairs = [(sb_names[i], agent_names[i]) for i in range(n_pairs)]

    def out(filename, content):
        write_file(os.path.join(tb_dir, filename), content)

    # Interfaces
    for a in agent_names:
        out(f"{a}_if.sv", gen_interface(proj, a))

    # Agent components
    for a in agent_names:
        out(f"{a}_seq_item.sv", gen_seq_item(proj, a))
        out(f"{a}_driver.sv",   gen_driver(proj, a))
        out(f"{a}_monitor.sv",  gen_monitor(proj, a))
        out(f"{a}_agent.sv",    gen_agent(proj, a))

    # Scoreboards
    for s, a in sb_pairs:
        out(f"{s}.sv", gen_scoreboard(proj, s, a))
    # Extra scoreboards without a paired agent use agent0
    for i in range(n_pairs, n_scoreboards):
        s = sb_names[i]
        a = agent_names[0]
        out(f"{s}.sv", gen_scoreboard(proj, s, a))

    # Virtual sequencer & sequence
    out(f"{proj}_virtual_sequencer.sv", gen_virtual_sequencer(proj, agent_names))
    out(f"{proj}_virtual_sequence.sv",  gen_virtual_sequence(proj, agent_names))

    # Environment
    # Build full sb_pairs list (extra SBs default to agent0)
    full_sb_pairs = sb_pairs[:]
    for i in range(n_pairs, n_scoreboards):
        full_sb_pairs.append((sb_names[i], agent_names[0]))
    out(f"{proj}_env.sv", gen_env(proj, agent_names, full_sb_pairs))

    # Test & tb_top
    out(f"{proj}_base_test.sv", gen_base_test(proj, agent_names))
    out(f"{proj}_tb_top.sv",    gen_tb_top(proj, agent_names))

    # Package
    out(f"{proj}_pkg.sv", gen_pkg(proj, agent_names, full_sb_pairs))

    # Filelist
    out(f"{proj}.f", gen_filelist(proj, agent_names, full_sb_pairs, tb_dir))

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

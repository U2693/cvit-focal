// Simple terminal-based Centurion CPU6 emulator/monitor.
//
// Build/run examples:
//   csc boots/cpu6.cs
//   mono boots/cpu6.exe --load program.bin 0100 --pc 0100
//   mono boots/cpu6.exe --floppy disk.img --boot-floppy --run
//   dotnet new console -o /tmp/cpu6emu && cp boots/cpu6.cs /tmp/cpu6emu/Program.cs && dotnet run --project /tmp/cpu6emu -- --load program.bin 0100 --pc 0100
//
// This is intentionally small and practical rather than cycle accurate.  The
// instruction behaviour is based on the public/experimental Centurion CPU6 notes
// in this repository.  Unknown opcodes stop execution with a diagnostic.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

public static class BiscvitProgram
{
    public static int Main(string[] args)
    {
        try
        {
            Cpu6 cpu = new Cpu6();
            bool headless = false;
            int maxSteps = 0;
            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i];
                if (a == "--help" || a == "-h") { Usage(); return 0; }
                if (a == "--load" && i + 2 < args.Length) cpu.Load(File.ReadAllBytes(args[++i]), Hex16(args[++i]));
                else if (a == "--pc" && i + 1 < args.Length) cpu.PC = Hex16(args[++i]);
                else if (a == "--sp" && i + 1 < args.Length) cpu.SetRegPair(Cpu6.SP, Hex16(args[++i]));
                else if (a == "--floppy" && i + 1 < args.Length) cpu.MountFloppy(args[++i]);
                else if (a == "--floppy-sector-size" && i + 1 < args.Length) cpu.FloppySectorSize = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
                else if (a == "--floppy-sectors-per-track" && i + 1 < args.Length) cpu.FloppySectorsPerTrack = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
                else if (a == "--floppy-heads" && i + 1 < args.Length) cpu.FloppyHeads = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
                else if (a == "--floppy-tracks" && i + 1 < args.Length) cpu.FloppyTracks = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
                else if (a == "--boot-floppy") cpu.BootFloppy();
                else if (a == "--run") headless = true;
                else if (a == "--max" && i + 1 < args.Length) maxSteps = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
                else throw new ArgumentException("bad argument: " + a);
            }
            if (headless) cpu.Run(maxSteps); else new Tui(cpu).Run();
            return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine("biscvit: " + ex.Message); return 1; }
    }

    static void Usage()
    {
        Console.WriteLine("usage: biscvit [--load file addr] [--pc addr] [--sp addr] [--floppy image] [--floppy-sector-size n] [--floppy-sectors-per-track n] [--floppy-heads n] [--floppy-tracks n] [--boot-floppy] [--run] [--max n]");
        Console.WriteLine("TUI keys: s step, r run/pause, n 100 steps, +/- speed, g goto memory, m edit memory, l load binary, b breakpoint, q/F10 quit");
    }
    public static ushort Hex16(string s)
    {
        s = s.StartsWith("0x", StringComparison.OrdinalIgnoreCase) ? s.Substring(2) : s;
        return UInt16.Parse(s, NumberStyles.HexNumber, CultureInfo.InvariantCulture);
    }
}

public sealed class Tui
{
    readonly Cpu6 cpu;
    readonly StringBuilder term = new StringBuilder();
    readonly ushort[] lastPairs = new ushort[8];
    ushort lastPc;
    ushort memAt;
    bool running;
    bool haveLast;
    bool followPc = true;
    int stepsPerTick = 250;
    long steps;
    string status = "ready";

    public Tui(Cpu6 cpu)
    {
        this.cpu = cpu;
        memAt = cpu.PC;
        Snapshot();
        cpu.TerminalOutput += ch => { if (ch == '\r') return; if (term.Length > 4096) term.Remove(0, 1024); term.Append(ch); };
    }

    public void Run()
    {
        bool oldCursor = true;
        try
        {
            try { Console.CursorVisible = false; } catch { }
            Draw();
            while (true)
            {
                if (running && !cpu.Halted)
                {
                    for (int i = 0; i < stepsPerTick && running && !cpu.Halted; i++)
                    {
                        if (cpu.Breakpoint >= 0 && cpu.PC == cpu.Breakpoint) { running = false; status = "breakpoint"; break; }
                        if (!StepOne()) break;
                    }
                    if (followPc) memAt = (ushort)(cpu.PC & 0xFFF0);
                    Draw();
                }
                if (!Console.KeyAvailable) { System.Threading.Thread.Sleep(running ? 1 : 25); continue; }
                var k = Console.ReadKey(true);
                if (k.Key == ConsoleKey.F10 || k.Key == ConsoleKey.Q) break;
                Handle(k); Draw();
            }
        }
        finally { Console.ResetColor(); try { Console.Clear(); } catch { } try { Console.CursorVisible = oldCursor; } catch { } }
    }

    bool StepOne()
    {
        try { cpu.Step(); steps++; return true; }
        catch (Exception ex) { running = false; status = ex.Message; return false; }
    }

    void Handle(ConsoleKeyInfo k)
    {
        try
        {
            switch (k.Key)
            {
                case ConsoleKey.S: running = false; if (!cpu.Halted) StepOne(); status = "stepped"; if (followPc) memAt = (ushort)(cpu.PC & 0xFFF0); break;
                case ConsoleKey.N: for (int i = 0; i < 100 && !cpu.Halted; i++) if (!StepOne()) break; status = "+100 steps"; if (followPc) memAt = (ushort)(cpu.PC & 0xFFF0); break;
                case ConsoleKey.R: running = !running; status = running ? "running" : "paused"; break;
                case ConsoleKey.Add:
                case ConsoleKey.OemPlus: stepsPerTick = Math.Min(50000, stepsPerTick * 2); status = "speed " + stepsPerTick + "/tick"; break;
                case ConsoleKey.Subtract:
                case ConsoleKey.OemMinus: stepsPerTick = Math.Max(1, stepsPerTick / 2); status = "speed " + stepsPerTick + "/tick"; break;
                case ConsoleKey.UpArrow: followPc = false; memAt -= 16; break;
                case ConsoleKey.DownArrow: followPc = false; memAt += 16; break;
                case ConsoleKey.PageUp: followPc = false; memAt -= 256; break;
                case ConsoleKey.PageDown: followPc = false; memAt += 256; break;
                case ConsoleKey.Home: followPc = true; memAt = (ushort)(cpu.PC & 0xFFF0); status = "following PC"; break;
                case ConsoleKey.G: { string s = Prompt("goto hex address"); if (s.Length > 0) { memAt = BiscvitProgram.Hex16(s); followPc = false; } break; }
                case ConsoleKey.P: { string s = Prompt("set PC"); if (s.Length > 0) { cpu.PC = BiscvitProgram.Hex16(s); followPc = true; } break; }
                case ConsoleKey.B: { string s = Prompt("breakpoint hex (blank clears)"); cpu.Breakpoint = s.Length == 0 ? -1 : BiscvitProgram.Hex16(s); break; }
                case ConsoleKey.L:
                    string f = Prompt("load binary file"); if (f.Length == 0) break;
                    string a = Prompt("load address"); if (a.Length == 0) break;
                    cpu.Load(File.ReadAllBytes(f), BiscvitProgram.Hex16(a)); status = "loaded " + f; break;
                case ConsoleKey.M:
                    EditMemory(); break;
                default:
                    if (!char.IsControl(k.KeyChar)) cpu.QueueTerminalInput((byte)k.KeyChar);
                    else if (k.Key == ConsoleKey.Enter) cpu.QueueTerminalInput((byte)'\n');
                    break;
            }
        }
        catch (Exception ex) { running = false; status = ex.Message; }
    }

    void EditMemory()
    {
        string a = Prompt("edit address");
        if (a.Length == 0) return;
        ushort addr = BiscvitProgram.Hex16(a);
        string bytes = Prompt("hex bytes");
        if (bytes.Length == 0) return;
        string[] parts = bytes.Split(new char[] { ' ', '\t', ',' }, StringSplitOptions.RemoveEmptyEntries);
        for (int i = 0; i < parts.Length; i++)
        {
            int v = Int32.Parse(parts[i], NumberStyles.HexNumber, CultureInfo.InvariantCulture);
            if (v < 0 || v > 0xFF) throw new ArgumentException("byte out of range: " + parts[i]);
            cpu.Poke((ushort)(addr + i), (byte)v);
        }
        memAt = (ushort)(addr & 0xFFF0);
        followPc = false;
        status = $"wrote {parts.Length} byte(s) at {addr:X4}";
    }

    string Prompt(string label)
    {
        int h = SafeHeight(), w = SafeWidth();
        var input = new StringBuilder();
        string prefix = label + ": ";
        try { Console.CursorVisible = true; } catch { }
        while (true)
        {
            string text = prefix + input;
            if (text.Length >= w) text = text.Substring(text.Length - w + 1);
            Put(0, h - 1, Pad(text, w));
            int cx = Math.Min(w - 1, text.Length);
            try { Console.SetCursorPosition(cx, h - 1); } catch { }

            var k = Console.ReadKey(true);
            if (k.Key == ConsoleKey.Enter) break;
            if (k.Key == ConsoleKey.Escape) { input.Clear(); break; }
            if (k.Key == ConsoleKey.Backspace) { if (input.Length > 0) input.Length--; continue; }
            if (!char.IsControl(k.KeyChar)) input.Append(k.KeyChar);
        }
        try { Console.CursorVisible = false; } catch { }
        return input.ToString().Trim();
    }

    void Draw()
    {
        int w = SafeWidth(), h = SafeHeight();
        if (w < 40 || h < 10) return;
        try { Console.Clear(); } catch { }
        Console.SetCursorPosition(0, 0);
        Console.ForegroundColor = ConsoleColor.White; Console.BackgroundColor = ConsoleColor.DarkBlue;
        Put(0, 0, Pad(" biscvit - Centurion CPU6 TUI emulator", w));
        Console.ResetColor();

        bool wide = w >= 104;
        if (wide)
        {
            int leftWidth = Math.Min(74, Math.Max(54, w / 2 - 2));
            int dividerX = leftWidth + 1;
            int rightX = dividerX + 2;
            int rightWidth = w - rightX;
            DrawDivider(dividerX, 1, h - 3);
            DrawRegs(0, 2, leftWidth);
            DrawMemory(0, 7, Math.Max(1, h - 11), leftWidth);
            int deviceRows = Math.Min(8, Math.Max(4, h / 5));
            int deviceY = h - deviceRows - 2;
            int terminalRows = Math.Max(1, deviceY - 3);
            DrawTerminal(rightX, 2, rightWidth, terminalRows);
            DrawDevices(rightX, deviceY, rightWidth, deviceRows);
        }
        else
        {
            int memRows = Math.Min(10, h / 2 - 5);
            DrawRegs(0, 2, w);
            DrawMemory(0, 7, Math.Max(1, memRows), w);
            DrawTerminal(0, 8 + memRows, w, Math.Max(1, h - memRows - 11));
        }

        Console.ForegroundColor = ConsoleColor.Yellow;
        Put(0, h - 2, Pad("s step  r run/pause  n +100  +/- speed  arrows/page mem  home follow-PC  g goto  m edit  p setpc  b break  l load  q quit", w));
        Console.ResetColor(); Put(0, h - 1, Pad("status: " + status + " | steps " + steps + " | speed " + stepsPerTick + "/tick" + (followPc ? " | follow PC" : ""), w));
        Snapshot();
    }

    void DrawDivider(int x, int y, int height)
    {
        Console.ForegroundColor = ConsoleColor.DarkGray;
        for (int i = 0; i < height; i++) PutRaw(x, y + i, "│");
        Console.ResetColor();
    }

    void DrawRegs(int x, int y, int width)
    {
        Put(x, y-1, BoxTitle(" CPU ", width));
        Put(x, y, Pad($"PC {cpu.PC:X4}  FLAGS {cpu.Flags}  IPL {cpu.Ipl:X1}  {(cpu.Halted ? "HALT" : running ? "RUN " : "PAUSE")}  BRK {(cpu.Breakpoint < 0 ? "----" : cpu.Breakpoint.ToString("X4"))}", width));
        DrawRegLine(x, y+1, new[] { Cpu6.AX, Cpu6.BX, Cpu6.RT, Cpu6.DX }, new[] { "AX", "BX", "RT", "DX" });
        DrawRegLine(x, y+2, new[] { Cpu6.EX, Cpu6.SP, Cpu6.GX, Cpu6.HX }, new[] { "EX", "SP", "GX", "HX" });
    }

    void DrawRegLine(int x, int y, int[] regs, string[] names)
    {
        int col = x;
        for (int i = 0; i < regs.Length; i++)
        {
            ushort v = cpu.GetRegPair(regs[i]);
            bool changed = haveLast && v != lastPairs[regs[i]];
            Console.ForegroundColor = changed ? ConsoleColor.Cyan : ConsoleColor.Gray;
            PutRaw(col, y, $"{names[i]} {v:X4}  ");
            col += 9;
        }
        Console.ResetColor();
    }

    void DrawMemory(int x, int y, int rows, int width)
    {
        Put(x, y-1, BoxTitle(" Memory ", width));
        for (int r = 0; r < rows; r++)
        {
            ushort a = (ushort)(memAt + r * 16);
            var line = new StringBuilder(); line.AppendFormat("{0:X4}: ", a);
            for (int i = 0; i < 16; i++) line.AppendFormat("{0:X2} ", cpu.Peek((ushort)(a + i)));
            line.Append(' ');
            for (int i = 0; i < 16; i++) { byte b = cpu.Peek((ushort)(a + i)); line.Append(b >= 32 && b < 127 ? (char)b : '.'); }
            bool pcRow = cpu.PC >= a && cpu.PC < (ushort)(a + 16);
            if (pcRow) { Console.ForegroundColor = ConsoleColor.Black; Console.BackgroundColor = ConsoleColor.DarkYellow; }
            Put(x, y+r, Pad(line.ToString(), width));
            if (pcRow) Console.ResetColor();
        }
    }

    void DrawTerminal(int x, int y, int width, int height)
    {
        if (width <= 0 || height <= 0) return;
        Put(x, y-1, BoxTitle(" Terminal MMIO F201 ", width));
        string[] lines = term.ToString().Replace("\r", "").Split('\n');
        int start = Math.Max(0, lines.Length - height);
        for (int i = 0; i < height; i++)
        {
            string line = start + i < lines.Length ? lines[start + i] : "";
            if (line.Length > width) line = line.Substring(line.Length - width);
            Put(x, y+i, Pad(line, width));
        }
    }

    void DrawDevices(int x, int y, int width, int rows)
    {
        if (width <= 0 || rows <= 0) return;
        Put(x, y-1, BoxTitle(" Devices ", width));
        string[] lines = new string[]
        {
            $"Terminal F201  inq {cpu.TerminalInputCount}  out {term.Length} chars",
            $"Floppy F140    {(cpu.FloppyMounted ? "mounted" : "not mounted")}",
            $"  cmd {cpu.FloppyCommand:X2}  status {cpu.FloppyStatus:X2}  unit {cpu.FloppyUnit:X2}",
            $"  track {cpu.FloppyTrack:D2}  sector {cpu.FloppySector:D2}  head {cpu.FloppyHead:D1}  size {cpu.FloppySectorSize}",
            $"  geometry {cpu.FloppyTracks}T/{cpu.FloppyHeads}H/{cpu.FloppySectorsPerTrack}S",
            $"DMA            addr {cpu.DmaAddr:X4}  count {cpu.DmaCount:X4}  mode {cpu.DmaMode:X2}",
            $"Memory         64K RAM",
            $"Interrupts     IPL {cpu.Ipl:X1}  FLAGS {cpu.Flags}",
            $"Breakpoint     {(cpu.Breakpoint < 0 ? "----" : cpu.Breakpoint.ToString("X4"))}"
        };
        for (int i = 0; i < rows; i++)
            Put(x, y + i, Pad(i < lines.Length ? lines[i] : "", width));
    }

    void Snapshot()
    {
        for (int i = 0; i < lastPairs.Length; i++) lastPairs[i] = cpu.GetRegPair(i);
        lastPc = cpu.PC;
        haveLast = true;
    }

    static string BoxTitle(string s, int width)
    {
        if (width <= s.Length) return Pad(s, width);
        return s + new string('─', width - s.Length);
    }
    static int SafeWidth() { try { return Math.Max(1, Console.WindowWidth); } catch { return 80; } }
    static int SafeHeight() { try { return Math.Max(1, Console.WindowHeight); } catch { return 24; } }
    static string Pad(string s, int width) { if (width <= 0) return ""; if (s.Length > width) return s.Substring(0, width); return s + new string(' ', width - s.Length); }
    static void Put(int x, int y, string s)
    {
        int w = SafeWidth(), h = SafeHeight();
        if (x < 0 || y < 0 || x >= w || y >= h) return;
        try { Console.SetCursorPosition(x, y); Console.Write(Pad(s, Math.Min(s.Length, w - x))); } catch { }
    }
    static void PutRaw(int x, int y, string s)
    {
        int w = SafeWidth(), h = SafeHeight();
        if (x < 0 || y < 0 || x >= w || y >= h) return;
        try { Console.SetCursorPosition(x, y); Console.Write(Pad(s, Math.Min(s.Length, w - x))); } catch { }
    }
}

public sealed class Cpu6
{
    public const int AH = 0, AL = 1, BH = 2, BL = 3, RH = 4, RL = 5, DH = 6, DL = 7, EH = 8, EL = 9, SH = 10, SL = 11, GH = 12, GL = 13, HH = 14, HL = 15;
    public const int AX = 0, BX = 1, RT = 2, DX = 3, EX = 4, SP = 5, GX = 6, HX = 7;
    const byte C = 1, N = 2, Z = 4, I = 8;

    readonly byte[] mem = new byte[65536];
    readonly Queue<byte> terminalInput = new Queue<byte>();
    byte flags, ipl, op;
    ushort dmaAddr, dmaCount;
    byte dmaMode;
    byte floppyCommand, floppyStatus = 1, floppyUnit, floppyTrack, floppySector, floppyHead;
    byte[] floppyImage;
    string floppyPath;
    public int FloppyTracks { get; set; } = 77;
    public int FloppyHeads { get; set; } = 2;
    public int FloppySectorsPerTrack { get; set; } = 26;
    public int FloppySectorSize { get; set; } = 128;
    public ushort PC { get; set; }
    public bool Halted { get; private set; }
    public bool Trace { get; set; }
    public int Breakpoint = -1;
    public event Action<char> TerminalOutput;

    public Cpu6() { PC = 0x0100; SetRegPair(SP, 0xFFFE); }
    public void Load(byte[] bytes, ushort address) { if (address + bytes.Length > 65536) throw new ArgumentException("load does not fit memory"); Buffer.BlockCopy(bytes, 0, mem, address, bytes.Length); }
    public void MountFloppy(string path)
    {
        floppyPath = path;
        floppyImage = File.Exists(path) ? File.ReadAllBytes(path) : new byte[FloppyTracks * FloppyHeads * FloppySectorsPerTrack * FloppySectorSize];
        floppyStatus = 1;
        Console.WriteLine("mounted 8-inch floppy: {0} ({1} bytes{2})", path, floppyImage.Length, IsAllZero(floppyImage) ? ", blank" : "");
    }
    public void BootFloppy()
    {
        EnsureFloppy();
        if (IsAllZero(floppyImage)) throw new InvalidOperationException("floppy image is blank/all zero; nothing to boot");
        int n = Math.Min(floppyImage.Length, 0x10000 - 0x0100);
        Buffer.BlockCopy(floppyImage, 0, mem, 0x0100, n);
        PC = 0x0103;
        Console.WriteLine("booted floppy: loaded {0} bytes at 0100, PC=0103", n);
    }

    byte Read8(ushort a)
    {
        if (a == 0xF200) return (byte)(0x02 | (terminalInput.Count != 0 ? 0x01 : 0x00)); // MUX0 status: RX ready bit0, TX ready bit1
        if (a == 0xF201)
        {
            if (terminalInput.Count != 0) return terminalInput.Dequeue();
            return 0;
        }
        if (a >= 0xF140 && a <= 0xF145) return ReadFloppyReg(a);
        return mem[a];
    }
    void Write8(ushort a, int v)
    {
        byte b = (byte)v;
        if (a == 0xF200) return; // MUX0 control/config
        if (a == 0xF201) { var h = TerminalOutput; if (h != null) h((char)b); else Console.Write((char)b); return; }
        if (a >= 0xF140 && a <= 0xF145) { WriteFloppyReg(a, b); return; }
        mem[a] = b;
    }
    ushort Read16(ushort a) { return (ushort)((Read8(a) << 8) | Read8((ushort)(a + 1))); }
    void Write16(ushort a, int v) { Write8(a, v >> 8); Write8((ushort)(a + 1), v); }
    byte Fetch() { return Read8(PC++); }
    ushort Fetch16() { int hi = Fetch(); return (ushort)((hi << 8) | Fetch()); }

    byte Reg(int r) { return Read8((ushort)((ipl << 4) | (r & 15))); }
    void Reg(int r, int v) { Write8((ushort)((ipl << 4) | (r & 15)), v); }
    ushort RegPair(int r) { r = (r & 7) << 1; return (ushort)((Reg(r) << 8) | Reg(r + 1)); }
    public void SetRegPair(int r, ushort v) { r = (r & 7) << 1; Reg(r, v >> 8); Reg(r + 1, v); }
    void Push(ushort v) { ushort sp = (ushort)(RegPair(SP) - 2); Write16(sp, v); SetRegPair(SP, sp); }
    ushort Pop() { ushort sp = RegPair(SP); ushort v = Read16(sp); SetRegPair(SP, (ushort)(sp + 2)); return v; }

    void Flag8(int r, bool carryKnown, int carry)
    {
        flags = (byte)(flags & ~(N | Z | (carryKnown ? C : 0)));
        byte b = (byte)r; if (b == 0) flags |= Z; if ((b & 0x80) != 0) flags |= N; if (carryKnown && carry != 0) flags |= C;
    }
    void Flag16(int r, bool carryKnown, int carry)
    {
        flags = (byte)(flags & ~(N | Z | (carryKnown ? C : 0)));
        ushort w = (ushort)r; if (w == 0) flags |= Z; if ((w & 0x8000) != 0) flags |= N; if (carryKnown && carry != 0) flags |= C;
    }

    public void Run(int maxSteps)
    {
        int n = 0; Halted = false;
        while (!Halted)
        {
            if (Breakpoint >= 0 && PC == Breakpoint) { Console.WriteLine("break at {0:X4}", PC); break; }
            Step();
            if (maxSteps > 0 && ++n >= maxSteps) break;
        }
    }

    public void Step()
    {
        ushort oldpc = PC; op = Fetch();
        if (Trace) Console.Error.WriteLine("{0:X4}: {1:X2} {2} AX={3:X4} BX={4:X4} RT={5:X4} SP={6:X4}", oldpc, op, FlagString(), RegPair(AX), RegPair(BX), RegPair(RT), RegPair(SP));
        if (op < 0x10) Low(); else if (op < 0x20) Branch(); else if (op < 0x30) Misc8(); else if (op < 0x40) Misc16(); else if (op < 0x50) Alu8(); else if (op < 0x60) Alu16(); else if (op < 0x70) Rt(); else if (op < 0x80) Jump(); else LoadStore();
    }

    void Low()
    {
        switch (op)
        {
            case 0x00: Halted = true; break; case 0x01: break;
            case 0x02: flags |= N; break; case 0x03: flags &= unchecked((byte)~N); break;
            case 0x04: flags |= I; break; case 0x05: flags &= unchecked((byte)~I); break;
            case 0x06: flags |= C; break; case 0x07: flags &= unchecked((byte)~C); break;
            case 0x08: flags = 0; break;
            case 0x09: PC = RegPair(RT); SetRegPair(RT, Pop()); break;
            case 0x0A: case 0x0E: break;
            case 0x0F: ipl = 15; break; // rsys-ish convenience
            default: Unknown(); break;
        }
    }
    void Branch()
    {
        bool t;
        switch (op & 15)
        {
            case 0: t = (flags & C) != 0; break; case 1: t = (flags & C) == 0; break;
            case 2: t = (flags & N) != 0; break; case 3: t = (flags & N) == 0; break;
            case 4: t = (flags & Z) != 0; break; case 5: t = (flags & Z) == 0; break;
            case 6: t = (flags & (C | Z)) == 0; break; case 7: t = (flags & C) != 0; break;
            case 8: case 9: t = (flags & (Z | N)) != 0; break;
            default: t = false; break;
        }
        sbyte off = unchecked((sbyte)Fetch()); if (t) PC = (ushort)(PC + off);
    }
    ushort Indexed(int size) { byte idx = Fetch(); int r = idx >> 5; int off = (idx & 8) != 0 ? unchecked((sbyte)Fetch()) : 0; ushort a = RegPair(r); if ((idx & 7) == 1) SetRegPair(r, (ushort)(a + size)); else if ((idx & 7) == 2) { a = (ushort)(a - size); SetRegPair(r, a); } else if ((idx & 7) != 0) Unknown(); return (ushort)(a + off); }
    ushort Addr(int size, int mode)
    {
        ushort a; int indir = 0;
        switch (mode & 15)
        {
            case 0: a = PC; PC += (ushort)size; break; case 1: a = PC; PC += 2; indir = 1; break; case 2: a = PC; PC += 2; indir = 2; break;
            case 3: a = (ushort)(PC + unchecked((sbyte)Fetch())); indir = 1; break; case 4: a = (ushort)(PC + unchecked((sbyte)Fetch())); indir = 2; break;
            case 5: a = Indexed(size); break; default: a = RegPair(mode & 7); break;
        }
        while (indir-- > 0) a = Read16(a); return a;
    }
    void LoadStore() { int m = op & 15; bool b = (op & 0x40) != 0; ushort a; switch (op & 0x30) { case 0x00: a = Addr(1, m); Reg(b ? BL : AL, Read8(a)); Flag8(Reg(b ? BL : AL), false, 0); break; case 0x10: a = Addr(2, m); SetRegPair(b ? BX : AX, Read16(a)); Flag16(RegPair(b ? BX : AX), false, 0); break; case 0x20: a = Addr(1, m); Write8(a, Reg(b ? BL : AL)); break; case 0x30: a = Addr(2, m); Write16(a, RegPair(b ? BX : AX)); break; } }
    void Rt() { ushort a = Addr(2, op & 7); if ((op & 8) != 0) Write16(a, RegPair(RT)); else SetRegPair(RT, Read16(a)); Flag16(RegPair(RT), false, 0); }
    void Jump()
    {
        if (op == 0x76) { ipl = 15; return; }
        ushort n; switch (op & 7) { case 1: n = Fetch16(); break; case 2: n = Read16(Fetch16()); break; case 3: n = (ushort)(PC + unchecked((sbyte)Fetch())); break; case 5: n = (ushort)(RegPair(AX) + unchecked((sbyte)Fetch())); break; default: Unknown(); return; }
        if ((op & 8) != 0) { Push(RegPair(RT)); SetRegPair(RT, PC); } PC = n;
    }
    void Misc8()
    {
        int r = AL; if ((op & 8) == 0) { byte enc = Fetch(); if ((enc & 15) != 0) { if (op == 0x22 && enc == 0x32) flags |= Z; else Unknown(); return; } r = enc >> 4; }
        switch (op) { case 0x20: Inc8(r); break; case 0x21: Dec8(r); break; case 0x22: Reg(r, 0); Flag8(0, false, 0); break; case 0x23: Reg(r, ~Reg(r)); Flag8(Reg(r), false, 0); break; case 0x24: Shr8(r); break; case 0x25: Shl8(r); break; case 0x26: Rrc8(r); break; case 0x27: Rlc8(r); break; case 0x28: Inc8(AL); break; case 0x29: Dec8(AL); break; case 0x2A: Reg(AL, 0); Flag8(0, false, 0); break; case 0x2B: Reg(AL, ~Reg(AL)); Flag8(Reg(AL), false, 0); break; case 0x2C: Shr8(AL); break; case 0x2D: Shl8(AL); break; case 0x2E: byte e = Fetch(); SetRegPair((e & 15) >> 1, (ushort)(e >> 5)); break; case 0x2F: Dma(); break; default: Unknown(); break; }
    }
    void Misc16()
    {
        int r = AX; if ((op & 8) == 0) { byte enc = Fetch(); if ((enc & 15) != 0) { if (op == 0x22 && enc == 0x32) flags |= Z; else Unknown(); return; } r = enc >> 5; }
        switch (op) { case 0x30: Inc16(r); break; case 0x31: Dec16(r); break; case 0x32: SetRegPair(r, 0); Flag16(0, false, 0); break; case 0x33: SetRegPair(r, (ushort)~RegPair(r)); Flag16(RegPair(r), false, 0); break; case 0x34: Shr16(r); break; case 0x35: Shl16(r); break; case 0x36: Rrc16(r); break; case 0x37: Rlc16(r); break; case 0x38: Inc16(AX); break; case 0x39: Dec16(AX); break; case 0x3A: SetRegPair(AX, 0); Flag16(0, false, 0); break; case 0x3B: SetRegPair(AX, (ushort)~RegPair(AX)); Flag16(RegPair(AX), false, 0); break; case 0x3C: Shr16(AX); break; case 0x3D: Shl16(AX); break; case 0x3E: Inc16(RT); break; case 0x3F: Dec16(RT); break; }
    }
    void Alu8() { int s = AL, d = BL; if ((op & 8) == 0) { byte e = Fetch(); s = e >> 4; d = e & 15; } switch (op & 7) { case 0: Add8(d, s); break; case 1: Sub8(d, s); break; case 2: And8(d, s); break; case 3: Or8(d, s); break; case 4: Xor8(d, s); break; case 5: Reg(d, Reg(s)); Flag8(Reg(d), false, 0); break; default: Unknown(); break; } }
    void Alu16() { int s = AX, d = BX; if ((op & 8) == 0) { byte e = Fetch(); s = e >> 5; d = (e & 15) >> 1; } switch (op & 7) { case 0: Add16(d, s); break; case 1: Sub16(d, s); break; case 2: And16(d, s); break; case 3: Or16(d, s); break; case 4: Xor16(d, s); break; case 5: SetRegPair(d, RegPair(s)); Flag16(RegPair(d), false, 0); break; default: Unknown(); break; } }
    void Dma() { byte e = Fetch(); int rp = e >> 4; switch (e & 15) { case 0: dmaAddr = RegPair(rp); break; case 1: SetRegPair(rp, dmaAddr); break; case 2: dmaCount = RegPair(rp); break; case 3: SetRegPair(rp, dmaCount); break; case 4: dmaMode = (byte)rp; break; case 6: break; default: Unknown(); break; } }

    byte ReadFloppyReg(ushort a)
    {
        switch (a - 0xF140)
        {
            case 0: return floppyCommand;
            case 1: return floppyStatus;
            case 2: return floppyUnit;
            case 3: return floppyTrack;
            case 4: return floppySector;
            case 5: return floppyHead;
            default: return 0;
        }
    }
    void WriteFloppyReg(ushort a, byte v)
    {
        switch (a - 0xF140)
        {
            case 0: floppyCommand = v; ExecuteFloppyCommand(v); break;
            case 1: floppyStatus = v; break;
            case 2: floppyUnit = v; break;
            case 3: floppyTrack = v; break;
            case 4: floppySector = v; break;
            case 5: floppyHead = v; break;
        }
    }
    void ExecuteFloppyCommand(byte cmd)
    {
        floppyStatus = 0;
        try
        {
            switch (cmd)
            {
                case 0: floppyStatus = 1; return;
                case 1: FloppyTransfer(read: true); break;
                case 2: FloppyTransfer(read: false); break;
                case 3: floppyTrack = 0; break;
                default: throw new InvalidOperationException("bad floppy command");
            }
            floppyStatus = 1;
        }
        catch
        {
            floppyStatus = 0x81;
            throw;
        }
    }
    void FloppyTransfer(bool read)
    {
        EnsureFloppy();
        int sector = floppySector == 0 ? 0 : floppySector - 1;
        if (floppyTrack >= FloppyTracks || floppyHead >= FloppyHeads || sector < 0 || sector >= FloppySectorsPerTrack) throw new InvalidOperationException("floppy address out of range");
        int imageOffset = (((floppyTrack * FloppyHeads) + floppyHead) * FloppySectorsPerTrack + sector) * FloppySectorSize;
        if (imageOffset + FloppySectorSize > floppyImage.Length) throw new InvalidOperationException("floppy image is too small for requested sector");
        int count = dmaCount == 0 ? FloppySectorSize : Math.Min(dmaCount, (ushort)FloppySectorSize);
        if (dmaAddr + count > 65536) throw new InvalidOperationException("floppy DMA transfer crosses memory end");
        if (read) Buffer.BlockCopy(floppyImage, imageOffset, mem, dmaAddr, count);
        else { Buffer.BlockCopy(mem, dmaAddr, floppyImage, imageOffset, count); SaveFloppy(); }
    }
    void EnsureFloppy()
    {
        if (floppyImage == null) throw new InvalidOperationException("no floppy mounted; use --floppy image or monitor command: floppy image");
    }
    void SaveFloppy()
    {
        if (String.IsNullOrEmpty(floppyPath)) return;
        File.WriteAllBytes(floppyPath, floppyImage);
    }
    static bool IsAllZero(byte[] bytes)
    {
        if (bytes == null || bytes.Length == 0) return true;
        for (int i = 0; i < bytes.Length; i++) if (bytes[i] != 0) return false;
        return true;
    }

    void Inc8(int r) { int v = Reg(r) + 1; Reg(r, v); Flag8(v, false, 0); } void Dec8(int r) { int v = Reg(r) - 1; Reg(r, v); Flag8(v, false, 0); }
    void Add8(int d, int s) { int v = Reg(d) + Reg(s); Reg(d, v); Flag8(v, true, v & 0x100); } void Sub8(int d, int s) { int v = Reg(d) - Reg(s); Reg(d, v); Flag8(v, true, v & 0x100); }
    void And8(int d, int s) { int v = Reg(d) & Reg(s); Reg(d, v); Flag8(v, true, 0); } void Or8(int d, int s) { int v = Reg(d) | Reg(s); Reg(d, v); Flag8(v, true, 0); } void Xor8(int d, int s) { int v = Reg(d) ^ Reg(s); Reg(d, v); Flag8(v, true, 0); }
    void Shl8(int r) { int v = Reg(r); Reg(r, v << 1); Flag8(v << 1, true, v & 0x80); } void Shr8(int r) { int v = Reg(r); Reg(r, v >> 1); Flag8(v >> 1, true, v & 1); } void Rlc8(int r) { int v = Reg(r); int c = v & 0x80; v = ((v << 1) | ((flags & C) != 0 ? 1 : 0)) & 0xFF; Reg(r, v); Flag8(v, true, c); } void Rrc8(int r) { int v = Reg(r); int c = v & 1; v = (v >> 1) | ((flags & C) != 0 ? 0x80 : 0); Reg(r, v); Flag8(v, true, c); }
    void Inc16(int r) { int v = RegPair(r) + 1; SetRegPair(r, (ushort)v); Flag16(v, false, 0); } void Dec16(int r) { int v = RegPair(r) - 1; SetRegPair(r, (ushort)v); Flag16(v, false, 0); }
    void Add16(int d, int s) { int v = RegPair(d) + RegPair(s); SetRegPair(d, (ushort)v); Flag16(v, true, v & 0x10000); } void Sub16(int d, int s) { int v = RegPair(d) - RegPair(s); SetRegPair(d, (ushort)v); Flag16(v, true, v & 0x10000); }
    void And16(int d, int s) { int v = RegPair(d) & RegPair(s); SetRegPair(d, (ushort)v); Flag16(v, true, 0); } void Or16(int d, int s) { int v = RegPair(d) | RegPair(s); SetRegPair(d, (ushort)v); Flag16(v, true, 0); } void Xor16(int d, int s) { int v = RegPair(d) ^ RegPair(s); SetRegPair(d, (ushort)v); Flag16(v, true, 0); }
    void Shl16(int r) { int v = RegPair(r); SetRegPair(r, (ushort)(v << 1)); Flag16(v << 1, true, v & 0x8000); } void Shr16(int r) { int v = RegPair(r); SetRegPair(r, (ushort)(v >> 1)); Flag16(v >> 1, true, v & 1); } void Rlc16(int r) { int v = RegPair(r); int c = v & 0x8000; v = ((v << 1) | ((flags & C) != 0 ? 1 : 0)) & 0xFFFF; SetRegPair(r, (ushort)v); Flag16(v, true, c); } void Rrc16(int r) { int v = RegPair(r); int c = v & 1; v = (v >> 1) | ((flags & C) != 0 ? 0x8000 : 0); SetRegPair(r, (ushort)v); Flag16(v, true, c); }

    void Unknown() { throw new InvalidOperationException(String.Format("unknown/unsupported opcode {0:X2} near {1:X4}", op, (ushort)(PC - 1))); }
    string FlagString() { char[] s = new char[] { '-', '-', '-', '-' }; if ((flags & C) != 0) s[0] = 'C'; if ((flags & I) != 0) s[1] = 'I'; if ((flags & N) != 0) s[2] = 'N'; if ((flags & Z) != 0) s[3] = 'Z'; return new string(s); }
    public void PrintRegs() { Console.WriteLine("PC={0:X4} FLAGS={1} IPL={2:X1} AX={3:X4} BX={4:X4} RT={5:X4} DX={6:X4} EX={7:X4} SP={8:X4} GX={9:X4} HX={10:X4}", PC, FlagString(), ipl, RegPair(AX), RegPair(BX), RegPair(RT), RegPair(DX), RegPair(EX), RegPair(SP), RegPair(GX), RegPair(HX)); }
    public void Dump(ushort a, int len) { for (int i = 0; i < len; i += 16) { Console.Write("{0:X4}: ", (ushort)(a + i)); for (int j = 0; j < 16 && i + j < len; j++) Console.Write("{0:X2} ", Read8((ushort)(a + i + j))); Console.WriteLine(); } }
    public void Modify(ushort a)
    {
        Console.WriteLine("memory modify: hex byte(s), blank=next, -=previous, .=done");
        while (true)
        {
            Console.Write("{0:X4} {1:X2}: ", a, Read8(a));
            string line = Console.ReadLine();
            if (line == null) return;
            line = line.Trim();
            if (line == "." || line.Equals("q", StringComparison.OrdinalIgnoreCase)) return;
            if (line == "-") { a--; continue; }
            if (line.Length == 0) { a++; continue; }
            string[] bytes = line.Split(new char[] { ' ', '\t', ',' }, StringSplitOptions.RemoveEmptyEntries);
            for (int i = 0; i < bytes.Length; i++)
            {
                int v = Int32.Parse(bytes[i], NumberStyles.HexNumber, CultureInfo.InvariantCulture);
                if (v < 0 || v > 0xFF) throw new ArgumentException("byte out of range: " + bytes[i]);
                Write8(a, v); a++;
            }
        }
    }
    public void SetByName(string name, ushort v) { name = name.ToLowerInvariant(); if (name == "pc") PC = v; else if (name == "ax") SetRegPair(AX, v); else if (name == "bx") SetRegPair(BX, v); else if (name == "rt") SetRegPair(RT, v); else if (name == "dx") SetRegPair(DX, v); else if (name == "ex") SetRegPair(EX, v); else if (name == "sp") SetRegPair(SP, v); else if (name == "gx") SetRegPair(GX, v); else if (name == "hx") SetRegPair(HX, v); else throw new ArgumentException("unknown register " + name); }
    public ushort GetRegPair(int r) { return RegPair(r); }
    public byte Peek(ushort a) { return mem[a]; }
    public void Poke(ushort a, byte v) { Write8(a, v); }
    public string Flags { get { return FlagString(); } }
    public byte Ipl { get { return ipl; } }
    public int TerminalInputCount { get { return terminalInput.Count; } }
    public ushort DmaAddr { get { return dmaAddr; } }
    public ushort DmaCount { get { return dmaCount; } }
    public byte DmaMode { get { return dmaMode; } }
    public bool FloppyMounted { get { return floppyImage != null; } }
    public byte FloppyCommand { get { return floppyCommand; } }
    public byte FloppyStatus { get { return floppyStatus; } }
    public byte FloppyUnit { get { return floppyUnit; } }
    public byte FloppyTrack { get { return floppyTrack; } }
    public byte FloppySector { get { return floppySector; } }
    public byte FloppyHead { get { return floppyHead; } }
    public void QueueTerminalInput(byte b) { terminalInput.Enqueue(b); }
}

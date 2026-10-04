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
            bool halt = false;
            int maxSteps = 0;
            for (int i = 0; i < args.Length; i++)
            {
                string a = args[i];
                if (a == "--help" || a == "-h") { Usage(); return 0; }
                if (a == "--load" && i + 2 < args.Length) cpu.Load(File.ReadAllBytes(args[++i]), Hex16(args[++i]));
                else if (a == "--pc" && i + 1 < args.Length) cpu.PC = Hex16(args[++i]);
                else if (a == "--sp" && i + 1 < args.Length) cpu.SetRegPair(Cpu6.SP, Hex16(args[++i]));
                else if (a == "--boot-rom" && i + 1 < args.Length) { cpu.Load(File.ReadAllBytes(args[++i]), 0xFC00); cpu.PC = 0xFC00; }
                else if (a == "--type" && i + 1 < args.Length) QueueText(cpu, args[++i]);
                else if (a == "--trace") cpu.Trace = true;
                else if (a == "--floppy-trace") cpu.FloppyTrace = true;
                else if (a == "--ffc-linear-experimental") cpu.FfcLinear = true;
                else if (a == "--floppy" && i + 1 < args.Length) cpu.MountFloppy(args[++i]);
                else if (a == "--hawk" && i + 1 < args.Length) cpu.MountHawk(args[++i]);
                else if (a == "--hawk0" && i + 1 < args.Length) cpu.MountHawk(0, args[++i]);
                else if (a == "--hawk1" && i + 1 < args.Length) cpu.MountHawk(1, args[++i]);
                else if (a == "--hawk-sector-size" && i + 1 < args.Length) cpu.HawkSectorSize = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
                else if (a == "--hawk-sector-stride" && i + 1 < args.Length) cpu.HawkSectorStride = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
                else if (a == "--hawk-sectors-per-track" && i + 1 < args.Length) cpu.HawkSectorsPerTrack = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
                else if (a == "--hawk-heads" && i + 1 < args.Length) cpu.HawkHeads = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
                else if (a == "--hawk-image-offset" && i + 1 < args.Length) cpu.HawkImageOffset = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
                else if (a == "--floppy-sector-size" && i + 1 < args.Length) cpu.FloppySectorSize = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
                else if (a == "--floppy-sectors-per-track" && i + 1 < args.Length) cpu.FloppySectorsPerTrack = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
                else if (a == "--floppy-heads" && i + 1 < args.Length) cpu.FloppyHeads = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
                else if (a == "--floppy-tracks" && i + 1 < args.Length) cpu.FloppyTracks = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
                else if (a == "--boot-floppy") cpu.BootFloppy();
                else if (a == "--run") headless = true;
                else if (a == "--halt") halt = true;
                else if (a == "--max" && i + 1 < args.Length) maxSteps = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
                else throw new ArgumentException("bad argument: " + a);
            }
            if (headless) { if (!halt) cpu.Run(maxSteps); }
            else new Tui(cpu, startRunning: !halt).Run();
            return 0;
        }
        catch (Exception ex) { Console.Error.WriteLine("biscvit: " + ex.Message); return 1; }
    }

    static void Usage()
    {
        Console.WriteLine("usage: biscvit [--load file addr] [--pc addr] [--sp addr] [--boot-rom file] [--type text] [--trace] [--floppy-trace] [--ffc-linear-experimental] [--floppy image] [--hawk image|--hawk0 image] [--hawk1 image] [--boot-floppy] [--halt] [--run] [--max n]");
        Console.WriteLine("       floppy geometry: --floppy-sector-size n --floppy-sectors-per-track n --floppy-heads n --floppy-tracks n");
        Console.WriteLine("       Hawk geometry: --hawk-sector-size n --hawk-sector-stride n --hawk-sectors-per-track n --hawk-heads n --hawk-image-offset n");
        Console.WriteLine("TUI keys: terminal focus is always active; F1 run/pause, F2 step, F3 100 steps, F4 clear HALT, F5 reset CPU, F6 breakpoint, F10 quit");
    }
    static void QueueText(Cpu6 cpu, string text)
    {
        for (int i = 0; i < text.Length; i++)
        {
            char ch = text[i];
            if (ch == '\\' && i + 1 < text.Length)
            {
                char n = text[++i];
                if (n == 'n') ch = '\n';
                else if (n == 'r') ch = '\r';
                else if (n == 't') ch = '\t';
                else if (n == 'e') ch = '\x1B';
                else ch = n;
            }
            cpu.QueueTerminalInput((byte)ch);
        }
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
    readonly StringBuilder cookedInput = new StringBuilder();
    readonly ushort[] lastPairs = new ushort[8];
    ushort lastPc;
    ushort memAt;
    ushort resetPc;
    bool running;
    bool haveLast;
    bool followPc = true;
    int stepsPerTick = 250;
    int refreshMs = 100;
    long steps;
    string status = "ready";
    string[] frame = Array.Empty<string>();
    int frameWidth, frameHeight;

    public Tui(Cpu6 cpu, bool startRunning = true)
    {
        this.cpu = cpu;
        running = startRunning;
        memAt = cpu.PC;
        resetPc = cpu.PC;
        Snapshot();
        cpu.TerminalOutput += ch =>
        {
            int c = ch;
            if (c >= 0x80) c &= 0x7F; // Centurion terminal strings often carry the high bit.
            if (c == '\r') return;
            if (c == '\b') { if (term.Length > 0) term.Length--; return; }
            if (c == '\f') { term.Clear(); return; }
            if (term.Length > 4096) term.Remove(0, 1024);
            term.Append((char)c);
        };
    }

    public void Run()
    {
        bool oldCursor = true;
        try
        {
            try { Console.CursorVisible = false; } catch { }
            Draw();
            long lastDraw = Environment.TickCount64;
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
                    long now = Environment.TickCount64;
                    if (!running || cpu.Halted || now - lastDraw >= refreshMs) { Draw(); lastDraw = now; }
                }
                if (!Console.KeyAvailable) { System.Threading.Thread.Sleep(running ? 1 : 25); continue; }
                var k = Console.ReadKey(true);
                if (k.Key == ConsoleKey.F10) break;
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
                case ConsoleKey.F1:
                    if (cpu.Halted) cpu.ClearHalt();
                    running = !running;
                    status = running ? "running" : "paused";
                    return;
                case ConsoleKey.F2:
                    running = false;
                    if (!cpu.Halted) StepOne();
                    status = "stepped";
                    return;
                case ConsoleKey.F3:
                    running = false;
                    for (int i = 0; i < 100 && !cpu.Halted; i++) if (!StepOne()) break;
                    status = "+100 steps";
                    return;
                case ConsoleKey.F4:
                    cpu.ClearHalt();
                    status = "HALT cleared";
                    return;
                case ConsoleKey.F5:
                    ResetCpu();
                    return;
                case ConsoleKey.F6:
                    string s = Prompt("breakpoint hex (blank clears)");
                    cpu.Breakpoint = s.Length == 0 ? -1 : BiscvitProgram.Hex16(s);
                    status = cpu.Breakpoint < 0 ? "breakpoint cleared" : "breakpoint " + cpu.Breakpoint.ToString("X4");
                    return;
                default:
                    SendTerminalKey(k);
                    return;
            }
        }
        catch (Exception ex) { running = false; status = ex.Message; }
    }

    void ResetCpu()
    {
        string s = Prompt("reset PC (blank default " + resetPc.ToString("X4") + ")");
        ushort pc = s.Length == 0 ? resetPc : BiscvitProgram.Hex16(s);
        cpu.Reset(pc);
        resetPc = pc;
        running = false;
        followPc = true;
        memAt = (ushort)(cpu.PC & 0xFFF0);
        Snapshot();
        status = "CPU reset PC=" + pc.ToString("X4");
    }

    void SendTerminalKey(ConsoleKeyInfo k)
    {
        // COMMAND is line-oriented and its tiny parser dispatches on the first
        // character.  Do local cooking there so "s<backspace>.sta" reaches cvit
        // as just ".sta" instead of being rejected before backspace arrives.
        if (cpu.CvitMode == "COMMAND")
        {
            if (k.Key == ConsoleKey.Enter)
            {
                foreach (char ch in cookedInput.ToString()) cpu.QueueTerminalInput((byte)ch);
                cpu.QueueTerminalInput((byte)'\r');
                cookedInput.Clear();
                return;
            }
            if (k.Key == ConsoleKey.Backspace) { if (cookedInput.Length > 0) cookedInput.Length--; return; }
            if (k.Key == ConsoleKey.Escape) { cookedInput.Clear(); return; }
            if (!char.IsControl(k.KeyChar)) cookedInput.Append(k.KeyChar);
            return;
        }
        if ((k.Modifiers & ConsoleModifiers.Alt) != 0) cpu.QueueTerminalInput(0x1B);
        if ((k.Modifiers & ConsoleModifiers.Control) != 0 && k.Key >= ConsoleKey.A && k.Key <= ConsoleKey.Z)
        {
            cpu.QueueTerminalInput((byte)(k.Key - ConsoleKey.A + 1));
            return;
        }
        if (!char.IsControl(k.KeyChar)) cpu.QueueTerminalInput((byte)k.KeyChar);
        else if (k.Key == ConsoleKey.Enter) cpu.QueueTerminalInput((byte)'\r');
        else if (k.Key == ConsoleKey.Backspace) cpu.QueueTerminalInput(0x08);
        else if (k.Key == ConsoleKey.Tab) cpu.QueueTerminalInput(0x09);
        else if (k.Key == ConsoleKey.Escape) cpu.QueueTerminalInput(0x1B);
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
        if (w < 40 || h < 5) return;
        EnsureFrame(w, h);
        Console.SetCursorPosition(0, 0);
        Console.ForegroundColor = ConsoleColor.White; Console.BackgroundColor = ConsoleColor.DarkBlue;
        Put(0, 0, Pad($" biscvit console  PC {cpu.PC:X4}  {(cpu.Halted ? "HALT" : running ? "RUN" : "PAUSE")}  {status}", w));
        Console.ResetColor();

        DrawTerminal(0, 2, w, Math.Max(1, h - 3));
        DrawParserOverlay(w, h);
        DrawButtons(0, h - 1, w);
        Snapshot();
    }

    void DrawParserOverlay(int screenWidth, int screenHeight)
    {
        int width = Math.Min(46, Math.Max(32, screenWidth / 2));
        int x = Math.Max(0, screenWidth - width);
        int y = 2;
        if (screenHeight < y + 6) return;
        string[] lines = new[]
        {
            BoxTitle(" cvit parser ", width),
            Pad("mode   " + cpu.CvitMode, width),
            Pad("prefix " + cpu.CvitPrefixDisplay, width),
            Pad("file   " + cpu.CvitActiveFileDisplay, width),
            Pad("console " + CurrentConsoleLine(), width),
            Pad("edit    " + cookedInput, width),
            Pad("buffer  " + cpu.CommandLineBufferText, width),
            Pad("key     " + cpu.LastTerminalKeyDisplay, width),
        };
        Console.ForegroundColor = ConsoleColor.Yellow;
        Console.BackgroundColor = ConsoleColor.DarkBlue;
        for (int i = 0; i < lines.Length; i++) Put(x, y + i, lines[i]);
        Console.ResetColor();
    }

    string CurrentConsoleLine()
    {
        string s = term.ToString().Replace("\r", "");
        int i = s.LastIndexOf('\n');
        string line = i >= 0 ? s.Substring(i + 1) : s;
        if (line.Length > 32) line = line.Substring(line.Length - 32);
        return line;
    }

    void DrawButtons(int x, int y, int width)
    {
        string run = running ? "Pause" : "Run";
        string brk = cpu.Breakpoint < 0 ? "BRK ----" : $"BRK {cpu.Breakpoint:X4}";
        string[] buttons = new[]
        {
            $"[F1 {run}]",
            "[F2 Step]",
            "[F3 +100]",
            "[F4 ClrHalt]",
            "[F5 Reset]",
            $"[F6 {brk}]",
            "[F10 Quit]"
        };
        string line = string.Join(" ", buttons);
        if (line.Length > width) line = line.Substring(0, width);
        Console.ForegroundColor = ConsoleColor.Black;
        Console.BackgroundColor = ConsoleColor.Gray;
        Put(x, y, Pad(line, width));
        Console.ResetColor();
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
        Put(x, y+3, Pad("OP " + DecodeAt(cpu.PC), width));
    }

    string DecodeAt(ushort pc)
    {
        byte op = cpu.Peek(pc), b1 = cpu.Peek((ushort)(pc + 1)), b2 = cpu.Peek((ushort)(pc + 2));
        string bytes = $"{op:X2}";
        string inst, args = "";
        if (op < 0x10)
        {
            inst = op switch { 0x00 => "HALT", 0x01 => "NOP", 0x02 => "SF", 0x03 => "RF", 0x04 => "EI", 0x05 => "DI", 0x06 => "SL", 0x07 => "RL", 0x08 => "CL", 0x09 => "RSR", 0x0A => "RI", 0x0B => "RIM", 0x0D => "PCX", 0x0E => "DLY", 0x0F => "RSV", _ => "LOW" };
        }
        else if (op < 0x20)
        {
            sbyte off = unchecked((sbyte)b1);
            bytes += $" {b1:X2}";
            inst = BranchName(op & 15);
            args = $"{(ushort)(pc + 2 + off):X4}";
        }
        else if (op < 0x30)
        {
            inst = (op & 7) switch { 0 => "INRB", 1 => "DCRB", 2 => "CLRB", 3 => "NOTB", 4 => "SRLB", 5 => "SLLB", 6 => "RRCB", 7 => "RLCB", _ => "MISC8" };
            if ((op & 8) == 0) { bytes += $" {b1:X2}"; args = $"{ByteReg(b1 >> 4)}" + ((b1 & 15) != 0 ? $",#{(b1 & 15) + 1}" : ""); }
            else args = "AL";
            if (op == 0x2E) { bytes += $" {b1:X2}"; inst = "LDM"; args = $"{PairReg((b1 & 15) >> 1)},#{b1 >> 5:X}"; }
            if (op == 0x2F) { bytes += $" {b1:X2}"; inst = "DMA"; args = $"{b1:X2}"; }
        }
        else if (op < 0x40)
        {
            inst = (op & 7) switch { 0 => "INR", 1 => "DCR", 2 => "CLR", 3 => "NOT", 4 => "SRL", 5 => "SLL", 6 => "RRC", 7 => "RLC", _ => "MISC16" };
            if ((op & 8) == 0) { bytes += $" {b1:X2}"; args = $"{PairReg((b1 >> 4) >> 1)}" + ((b1 & 15) != 0 ? $",#{(b1 & 15) + 1}" : ""); }
            else args = (op == 0x3E || op == 0x3F) ? "RT" : "AX";
        }
        else if (op < 0x50)
        {
            inst = (op & 7) switch { 0 => "ADDB", 1 => "SUBB", 2 => "ANDB", 3 => "ORB", 4 => "XORB", 5 => "XFRB", 7 => "MEM", _ => "ALU8" };
            if (op == 0x47) { bytes += $" {b1:X2} {b2:X2} ..."; args = MemArgs(pc); }
            else if ((op & 8) == 0) { bytes += $" {b1:X2}"; args = $"{ByteReg(b1 >> 4)},{ByteReg(b1 & 15)}"; }
            else args = $"AL,{ImplicitByteDest(op)}";
        }
        else if (op < 0x60)
        {
            inst = (op & 7) switch { 0 => "ADD", 1 => "SUB", 2 => "AND", 3 => "OR", 4 => "XOR", 5 => "XFR", _ => "ALU16" };
            if ((op & 8) == 0)
            {
                bytes += $" {b1:X2}";
                int mode = b1 & 0x11;
                if (mode != 0) bytes += $" {b2:X2} {cpu.Peek((ushort)(pc + 3)):X2}";
                args = Alu16Args(pc, b1, mode);
            }
            else args = $"AX,{ImplicitWordDest(op)}";
        }
        else if (op == 0x66)
        {
            bytes += $" {b1:X2}";
            inst = "SVC";
            args = $"#{b1:X2}";
        }
        else if (op == 0x67 && b1 == 0x4A && b2 == 0x86)
        {
            bytes += $" {b1:X2} {b2:X2}";
            inst = "MEMCPY";
            args = "AL+1,[EX],[DX]";
        }
        else if (op < 0x70)
        {
            var a = AddrArg(pc, 2, op & 7, out int len);
            bytes += Bytes(pc, 1, len - 1);
            inst = (op & 8) != 0 ? "STR" : "LDR";
            args = (op & 8) != 0 ? $"RT,{a}" : $"RT,{a}";
        }
        else if (op < 0x80)
        {
            if (op == 0x7E || op == 0x7F) { bytes += $" {b1:X2}"; inst = op == 0x7E ? "PUSH" : "POP"; args = ByteRange(b1); }
            else
            {
                var a = JumpArg(pc, op & 7, out int len);
                bytes += Bytes(pc, 1, len - 1);
                inst = (op & 8) != 0 ? "CALL" : "JMP";
                args = a;
            }
        }
        else if (op == 0xD7 || op == 0xE6)
        {
            bytes += $" {b1:X2}";
            inst = op == 0xD7 ? "ILST" : "ILLD";
            args = $"IL{b1 >> 4}({PairReg((b1 & 15) >> 1)}),AX";
        }
        else if (op == 0xF6)
        {
            bytes += $" {b1:X2} {b2:X2}";
            inst = "XIO";
            args = $"{ByteReg((b1 & 0x20) != 0 ? Cpu6.BL : Cpu6.AL)},[EX{unchecked((sbyte)b2):+0;-0;0}]";
        }
        else
        {
            int m = op & 15;
            var a = AddrArg(pc, ((op & 0x10) != 0) ? 2 : 1, m, out int len);
            bytes += Bytes(pc, 1, len - 1);
            bool word = (op & 0x10) != 0, b = (op & 0x40) != 0;
            bool store = (op & 0x20) != 0;
            inst = (store ? "ST" : "LD") + (word ? "" : "B");
            string r = word ? (b ? "BX" : "AX") : (b ? "BL" : "AL");
            args = store ? $"{r},{a}" : $"{r},{a}";
        }
        return $"{pc:X4}: {bytes,-14} {inst} {args}".TrimEnd();
    }

    string BranchName(int n) => n switch { 0 => "BC", 1 => "BNC", 2 => "BN", 3 => "BP", 4 => "BZ", 5 => "BNZ", 6 => "BLT", 7 => "BGE", 8 => "BGT", 9 => "BLE", 10 => "BS1", 11 => "BS2", 12 => "BS3", 13 => "BS4", _ => "BR" };
    string PairReg(int r) => (r & 7) switch { 0 => "AX", 1 => "BX", 2 => "RT", 3 => "DX", 4 => "EX", 5 => "SP", 6 => "GX", _ => "HX" };
    string ByteReg(int r) => (r & 15) switch { 0 => "AH", 1 => "AL", 2 => "BH", 3 => "BL", 4 => "RH", 5 => "RL", 6 => "DH", 7 => "DL", 8 => "EH", 9 => "EL", 10 => "SH", 11 => "SL", 12 => "GH", 13 => "GL", 14 => "HH", _ => "HL" };
    string ImplicitWordDest(int op) => op switch { 0x5B => "RT", 0x5C => "DX", 0x5D => "BX", 0x5E => "EX", 0x5F => "SP", _ => "BX" };
    string ImplicitByteDest(int op) => op switch { 0x4B => "RL", 0x4C => "DL", 0x4D => "BL", 0x4E => "EL", 0x4F => "SL", _ => "BL" };
    string Bytes(ushort pc, int start, int count) { var s = new StringBuilder(); for (int i = 0; i < count; i++) s.Append($" {cpu.Peek((ushort)(pc + start + i)):X2}"); return s.ToString(); }
    ushort WordAt(ushort a) => (ushort)((cpu.Peek(a) << 8) | cpu.Peek((ushort)(a + 1)));
    string JumpArg(ushort pc, int mode, out int len)
    {
        len = 1;
        if (mode == 1) { len = 3; return $"{WordAt((ushort)(pc + 1)):X4}"; }
        if (mode == 2) { len = 3; return $"[{WordAt((ushort)(pc + 1)):X4}]"; }
        if (mode == 3) { len = 2; return $"{(ushort)(pc + 2 + unchecked((sbyte)cpu.Peek((ushort)(pc + 1)))):X4}"; }
        if (mode == 4) { len = 2; return $"[{(ushort)(pc + 2 + unchecked((sbyte)cpu.Peek((ushort)(pc + 1)))):X4}]"; }
        if (mode == 5) { len = 2; return $"[AX{unchecked((sbyte)cpu.Peek((ushort)(pc + 1))):+0;-0;0}]"; }
        return "?";
    }
    string AddrArg(ushort pc, int size, int mode, out int len)
    {
        len = 1;
        if (mode == 0) { len = 1 + size; return size == 1 ? $"#{cpu.Peek((ushort)(pc + 1)):X2}" : $"#{WordAt((ushort)(pc + 1)):X4}"; }
        if (mode == 1) { len = 3; return $"{WordAt((ushort)(pc + 1)):X4}"; }
        if (mode == 2) { len = 3; return $"[{WordAt((ushort)(pc + 1)):X4}]"; }
        if (mode == 3) { len = 2; return $"{(ushort)(pc + 2 + unchecked((sbyte)cpu.Peek((ushort)(pc + 1)))):X4}"; }
        if (mode == 4) { len = 2; return $"[{(ushort)(pc + 2 + unchecked((sbyte)cpu.Peek((ushort)(pc + 1)))):X4}]"; }
        if (mode == 5) return IndexedArg(pc, size, out len);
        return PairReg(mode & 7);
    }
    string IndexedArg(ushort pc, int size, out int len)
    {
        byte idx = cpu.Peek((ushort)(pc + 1));
        len = ((idx & 8) != 0) ? 3 : 2;
        string r = PairReg((idx >> 4) >> 1);
        string pre = (idx & 3) == 2 ? "-" : "";
        string post = (idx & 3) == 1 ? "+" : "";
        string disp = (idx & 8) != 0 ? $"{unchecked((sbyte)cpu.Peek((ushort)(pc + 2))):+0;-0;0}" : "";
        string s = $"[{pre}{r}{post}{disp}]";
        return (idx & 4) != 0 ? $"@{s}" : s;
    }
    string Alu16Args(ushort pc, byte e, int mode)
    {
        string s = PairReg((e >> 4) >> 1), d = PairReg((e & 15) >> 1);
        if (mode == 0) return $"{s},{d}";
        ushort w = WordAt((ushort)(pc + 2));
        string src = (mode & 1) != 0 ? $"[{w:X4}]" : $"#{w:X4}";
        if (mode == 0x11) src = $"[{s}+{w:X4}]";
        return $"{src},{d}";
    }
    string ByteRange(byte e) => $"{ByteReg(e >> 4)}..{ByteReg(((e >> 4) + (e & 15)) & 15)}";
    string MemArgs(ushort pc)
    {
        byte ib = cpu.Peek((ushort)(pc + 1));
        int selector = ib >> 4;
        if (selector == 4 || selector == 9) return $"#{cpu.Peek((ushort)(pc + 3)):X2},{WordAt((ushort)(pc + 4)):X4},len {cpu.Peek((ushort)(pc + 2)) + 1}";
        return $"{ib:X2}";
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

    void DrawHelp(int x, int y, int width)
    {
        if (width <= 0) return;
        Put(x, y - 1, BoxTitle(" Help ", width));
        Console.ForegroundColor = ConsoleColor.Yellow;
        Put(x, y,     Pad("Alt-= focus terminal   s step   r run/pause   n +100", width));
        Put(x, y + 1, Pad("c clear HALT   Ctrl-R reset   +/- speed   [/ ] refresh", width));
        Put(x, y + 2, Pad("arrows/page memory   g goto   m edit   p PC   b break   q quit", width));
        Console.ResetColor();
    }

    void DrawTerminal(int x, int y, int width, int height)
    {
        if (width <= 0 || height <= 0) return;
        Put(x, y-1, BoxTitle(" Console MMIO F201 ", width));
        string display = term.ToString();
        if (cpu.CvitMode == "COMMAND" && cookedInput.Length != 0) display += cookedInput.ToString();
        string[] lines = display.Replace("\r", "").Split('\n');
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
            $"FFC F800       cmd {cpu.FfcCommand:X2}  status {cpu.FfcStatus:X2}  result {cpu.FfcResult:X2}  buflen {cpu.FfcCommandLength}",
            $"Hawk F140      {(cpu.HawkMounted ? "mounted" : "not mounted")} cmd {cpu.HawkCommand:X2} status {cpu.HawkStatus:X2}/{cpu.HawkDriveStatus:X2}",
            $"  unit {cpu.HawkUnit:X2} addr {cpu.HawkSectorAddress:X4} cyl {cpu.HawkCylinder} head {cpu.HawkHead} sec {cpu.HawkSector}",
            $"Memory         64K RAM",
            $"Interrupts     IPL {cpu.Ipl:X1}  depth {cpu.InterruptDepth}  FLAGS {cpu.Flags}",
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
    void EnsureFrame(int w, int h)
    {
        if (frameWidth == w && frameHeight == h && frame.Length == h) return;
        frameWidth = w;
        frameHeight = h;
        frame = new string[h];
        for (int i = 0; i < h; i++) frame[i] = new string('\0', w);
        try { Console.Clear(); } catch { }
    }
    void InvalidateFrameRow(int y)
    {
        if (y >= 0 && y < frame.Length) frame[y] = new string('\0', frameWidth);
    }
    void Put(int x, int y, string s)
    {
        int w = SafeWidth(), h = SafeHeight();
        if (x < 0 || y < 0 || x >= w || y >= h) return;
        string text = Pad(s, Math.Min(s.Length, w - x));
        if (frame.Length == h && y < frame.Length && frame[y].Length == w)
        {
            string old = frame[y].Substring(x, text.Length);
            if (old == text) return;
            var row = new StringBuilder(frame[y]);
            row.Remove(x, text.Length);
            row.Insert(x, text);
            frame[y] = row.ToString();
        }
        try { Console.SetCursorPosition(x, y); Console.Write(text); } catch { }
    }
    void PutRaw(int x, int y, string s) => Put(x, y, s);
}

public sealed class CvitFileSystem
{
    public const int PageSize = 200;
    public const int SystemDataSector = 0x20;
    public const int SystemUalSector = 0x12;
    const int DirectoryRowSize = 16;
    const int DirectoryFirstRow = 16;
    const int DirectoryPageBytes = PageSize;
    const int MemberNameLength = 10;

    readonly byte[] image;
    readonly Func<int, int> imageOffsetForSector;
    readonly int sectorSize;
    readonly Action save;

    public CvitFileSystem(byte[] image, Func<int, int> imageOffsetForSector, int sectorSize, Action save)
    {
        this.image = image;
        this.imageOffsetForSector = imageOffsetForSector;
        this.sectorSize = sectorSize;
        this.save = save;
    }

    public bool TryReadMember(string name, out byte[] data)
    {
        data = Array.Empty<byte>();
        if (!TryFindMember(name, out int page, out int capacity)) return false;
        int offset = MemberOffset(page);
        int end = capacity;
        while (end > 0 && (image[offset + end - 1] == 0 || image[offset + end - 1] == 0x20)) end--;
        data = new byte[end];
        Buffer.BlockCopy(image, offset, data, 0, end);
        return true;
    }

    public bool TryReadTextMember(string name, out string text)
    {
        text = "";
        if (!TryReadMember(name, out byte[] data)) return false;
        text = Encoding.ASCII.GetString(data);
        return true;
    }

    public bool WriteTextMember(string name, string text, bool createIfMissing, out string error)
    {
        error = "";
        if (!TryFindMember(name, out int page, out int capacity))
        {
            if (!createIfMissing || !CreateFixedMember(name, "TXT")) { error = "?NO FILE"; return false; }
            if (!TryFindMember(name, out page, out capacity)) { error = "?NO FILE"; return false; }
        }
        byte[] data = Encoding.ASCII.GetBytes(text);
        if (data.Length > capacity) { error = "?TOO BIG"; return false; }
        int offset = MemberOffset(page);
        Array.Fill<byte>(image, 0x20, offset, capacity);
        Buffer.BlockCopy(data, 0, image, offset, data.Length);
        save();
        return true;
    }

    public bool CreateFixedMember(string name, string type = "TXT")
    {
        if (String.IsNullOrWhiteSpace(name) || name.Length > MemberNameLength) return false;
        if (TryFindMember(name, out _, out _)) return true;
        int dir = imageOffsetForSector(SystemDataSector);
        if (!RangeOk(dir, sectorSize)) return false;
        int term = -1;
        for (int row = DirectoryFirstRow; row < DirectoryPageBytes; row += DirectoryRowSize)
        {
            if (image[dir + row] == 0x84 && image[dir + row + 1] == 0x8D) { term = row; break; }
        }
        if (term < 0 || term + DirectoryRowSize + 1 >= DirectoryPageBytes) return false;

        int ual = imageOffsetForSector(SystemUalSector);
        if (!RangeOk(ual, sectorSize)) return false;
        int nsec = ((image[ual] << 8) | image[ual + 1]) + 1;
        int newSector = SystemDataSector + nsec;
        int newPage = nsec * 2;
        int newOff = imageOffsetForSector(newSector);
        if (!RangeOk(newOff, sectorSize)) return false;

        WriteDirectoryRow(dir + term, name, newPage, TypeCode(type));
        image[dir + term + DirectoryRowSize] = 0x84;
        image[dir + term + DirectoryRowSize + 1] = 0x8D;

        Array.Fill<byte>(image, 0x20, newOff, sectorSize);
        image[ual] = (byte)(nsec >> 8);
        image[ual + 1] = (byte)nsec;
        AppendSystemUalSector(newSector);
        save();
        return true;
    }

    public IReadOnlyList<(string Name, string Type)> ListMembers()
    {
        int dir = imageOffsetForSector(SystemDataSector);
        if (!RangeOk(dir, sectorSize)) return Array.Empty<(string, string)>();
        var entries = new List<(string Name, string Type)>();
        foreach (var entry in DirectoryEntries(dir)) entries.Add((entry.Name, TypeName(entry.Type)));
        return entries;
    }

    public bool LooksLikeSystemVolume()
    {
        return TryFindMember("KERNEL", out _, out _) && TryFindMember("COMMAND", out _, out _);
    }

    public bool TryFindMember(string name, out int page, out int capacity)
    {
        page = 0; capacity = 0;
        int dir = imageOffsetForSector(SystemDataSector);
        if (!RangeOk(dir, sectorSize)) return false;
        int found = -1, next = Int32.MaxValue;
        foreach (var entry in DirectoryEntries(dir))
        {
            if (String.Equals(entry.Name, name, StringComparison.OrdinalIgnoreCase)) found = entry.Page;
        }
        if (found < 0) return false;
        foreach (var entry in DirectoryEntries(dir))
            if (entry.Page > found && entry.Page < next) next = entry.Page;
        page = found;
        capacity = (next == Int32.MaxValue ? 2 : next - found) * PageSize;
        return capacity > 0;
    }

    int MemberOffset(int page) => imageOffsetForSector(SystemDataSector + page / 2) + (page & 1) * PageSize;
    bool RangeOk(int offset, int count) => offset >= 0 && offset + count <= image.Length;

    IEnumerable<(string Name, int Page, byte Type)> DirectoryEntries(int dir)
    {
        for (int row = DirectoryFirstRow; row < sectorSize; row += DirectoryRowSize)
        {
            if (image[dir + row] == 0x84 && image[dir + row + 1] == 0x8D) yield break;
            yield return (DecodeMemberName(dir + row), image[dir + row + 10] + Math.Max(0, image[dir + row + 12] - 0x08) * 128, image[dir + row + 13]);
        }
    }

    static byte TypeCode(string type) => String.Equals(type, "TXT", StringComparison.OrdinalIgnoreCase) ? (byte)0x04 : (byte)0x14;
    static string TypeName(byte type) => type == 0x04 ? "TXT" : "SYS";

    void WriteDirectoryRow(int offset, string name, int page, byte type)
    {
        for (int i = 0; i < MemberNameLength; i++)
            image[offset + i] = (byte)(((i < name.Length ? name[i] : ' ') & 0x7F) | 0x80);
        image[offset + 10] = (byte)(page % 128);
        image[offset + 11] = 0;
        image[offset + 12] = (byte)(0x08 + page / 128);
        image[offset + 13] = type;
        image[offset + 14] = 0;
        image[offset + 15] = 0;
    }

    string DecodeMemberName(int offset)
    {
        var b = new StringBuilder();
        for (int i = 0; i < MemberNameLength; i++)
        {
            char c = (char)(image[offset + i] & 0x7F);
            if (c != ' ') b.Append(c);
        }
        return b.ToString();
    }

    void AppendSystemUalSector(int sector)
    {
        for (int us = 0; us < 6; us++)
        {
            int off = imageOffsetForSector(SystemUalSector + us);
            int start = us == 0 ? 6 : 0;
            for (int p = start; p <= sectorSize - 3; p += 3)
            {
                if (image[off + p] == 0xFF && image[off + p + 1] == 0xFF && image[off + p + 2] == 0xFF)
                {
                    image[off + p] = (byte)(sector >> 16);
                    image[off + p + 1] = (byte)(sector >> 8);
                    image[off + p + 2] = (byte)sector;
                    if (p + 5 < sectorSize)
                    {
                        image[off + p + 3] = 0xFF;
                        image[off + p + 4] = 0xFF;
                        image[off + p + 5] = 0xFF;
                    }
                    return;
                }
            }
        }
    }
}

public sealed class Cpu6
{
    public const int AH = 0, AL = 1, BH = 2, BL = 3, RH = 4, RL = 5, DH = 6, DL = 7, EH = 8, EL = 9, SH = 10, SL = 11, GH = 12, GL = 13, HH = 14, HL = 15;
    public const int AX = 0, BX = 1, RT = 2, DX = 3, EX = 4, SP = 5, GX = 6, HX = 7;
    const byte C = 1, N = 2, Z = 4, I = 8;

    const ushort CommandLineBuffer = 0x2F00;

    readonly byte[] mem = new byte[65536];
    readonly Queue<byte> terminalInput = new Queue<byte>();
    byte flags, ipl, op;
    byte lastTerminalKey;
    bool haveLastTerminalKey;
    bool debugDepositActive;
    ushort debugDepositAddr;
    readonly StringBuilder debugDepositInput = new StringBuilder();
    bool cedActive;
    bool keyTraceActive;
    readonly StringBuilder cedInput = new StringBuilder();
    readonly SortedDictionary<int, string> cedLines = new SortedDictionary<int, string>();
    string cedActiveFile = "TEST";
    string cedActiveDisplay = "H0:/SYSTEM/TEST";
    int currentCvitDevice;
    string currentCvitPrefix = "/SYSTEM";
    readonly Stack<InterruptFrame> interruptStack = new Stack<InterruptFrame>();
    ushort dmaAddr, dmaCount;
    byte dmaMode;
    byte floppyCommand, floppyStatus = 1, floppyUnit, floppyTrack, floppySector, floppyHead;
    byte ffcCommand, ffcStatus = 1, ffcResult;
    byte hawkUnit, hawkWriteMask, hawkCommand, hawkStatus, hawkDriveStatus = 0x3F;
    ushort hawkSectorAddress;
    byte[] ffcCommandBuffer = new byte[0];
    byte[] floppyImage, hawkImage;
    readonly byte[][] hawkImages = new byte[2][];
    bool muxInterruptEnabled;
    string floppyPath, hawkPath;
    readonly string[] hawkPaths = new string[2];
    CvitFileSystem cvitFs;
    readonly CvitFileSystem[] cvitFileSystems = new CvitFileSystem[2];
    public int FloppyTracks { get; set; } = 77;
    public int FloppyHeads { get; set; } = 2;
    public int FloppySectorsPerTrack { get; set; } = 26;
    public int FloppySectorSize { get; set; } = 128;
    public int HawkSectorSize { get; set; } = 400;
    public int HawkSectorStride { get; set; } = 512;
    public int HawkSectorsPerTrack { get; set; } = 16;
    public int HawkHeads { get; set; } = 2;
    public int HawkImageOffset { get; set; } = -1;
    public ushort PC { get; set; }
    public bool Halted { get; private set; }
    public bool Trace { get; set; }
    public bool FloppyTrace { get; set; }
    public bool FfcLinear { get; set; }
    public int Breakpoint = -1;
    public event Action<char> TerminalOutput;

    struct InterruptFrame
    {
        public byte Ipl;
        public ushort Pc;
        public byte Flags;
        public InterruptFrame(byte ipl, ushort pc, byte flags) { Ipl = ipl; Pc = pc; Flags = flags; }
    }

    public Cpu6() { Reset(); }
    public void ClearHalt() { Halted = false; }
    public void Reset() { Reset(0x0100); }
    public void Reset(ushort pc)
    {
        Array.Clear(mem, 0, 0x100); // CPU6 interlevel registers live in low memory.
        flags = 0;
        ipl = 0;
        op = 0;
        interruptStack.Clear();
        dmaAddr = 0;
        dmaCount = 0;
        dmaMode = 0;
        muxInterruptEnabled = false;
        PC = pc;
        SetRegPair(SP, 0xFFFE);
        Halted = false;
    }
    public void Load(byte[] bytes, ushort address) { if (address + bytes.Length > 65536) throw new ArgumentException("load does not fit memory"); Buffer.BlockCopy(bytes, 0, mem, address, bytes.Length); }
    public void MountFloppy(string path)
    {
        floppyPath = path;
        floppyImage = File.Exists(path) ? File.ReadAllBytes(path) : new byte[FloppyTracks * FloppyHeads * FloppySectorsPerTrack * FloppySectorSize];
        floppyStatus = 1;
        Console.WriteLine("mounted 8-inch floppy: {0} ({1} bytes{2})", path, floppyImage.Length, IsAllZero(floppyImage) ? ", blank" : "");
    }
    public void MountHawk(string path) => MountHawk(0, path);
    public void MountHawk(int unit, string path)
    {
        if (unit < 0 || unit >= hawkImages.Length) throw new ArgumentException("bad Hawk unit: " + unit);
        byte[] image = File.Exists(path) ? File.ReadAllBytes(path) : new byte[HawkSectorStride * HawkSectorsPerTrack * HawkHeads * 203];
        if (HawkImageOffset < 0) HawkImageOffset = DetectHawkImageOffset(image);
        hawkImages[unit] = image;
        hawkPaths[unit] = path;
        cvitFileSystems[unit] = new CvitFileSystem(image, HawkImageOffsetForLogicalSector, HawkSectorSize, () => SaveHawk(unit));
        if (unit == 0)
        {
            hawkImage = image;
            hawkPath = path;
            cvitFs = cvitFileSystems[unit];
        }
        hawkStatus = 0;
        hawkDriveStatus = 0x3F;
        Console.WriteLine("mounted Hawk H{0}: {1} ({2} bytes, data offset {3}{4})", unit, path, image.Length, HawkImageOffset, IsAllZero(image) ? ", blank" : "");
    }
    int DetectHawkImageOffset(byte[] image)
    {
        // Most known platter dumps have the HDIPL sector at byte 0 and a 304-byte
        // trailer.  Some dump formats have a short textual/header prefix.  Prefer
        // the recognizable WIPL/HDIPL entry bytes over the old modulo heuristic,
        // which mistook CENTOS_*.IMG's trailer for a leading header.
        int[] candidates = { 0, 12, 304 };
        foreach (int offset in candidates)
            if (LooksLikeHawkIpl(image, offset)) return offset;
        return 0;
    }
    bool LooksLikeHawkIpl(byte[] image, int offset)
    {
        return image.Length >= offset + 8 && image[offset] == 0x01 && image[offset + 1] == 0x01 && image[offset + 2] == 0x01 && image[offset + 3] == 0x73;
    }
    public void BootFloppy()
    {
        EnsureFloppy();
        if (IsAllZero(floppyImage)) throw new InvalidOperationException("floppy image is blank/all zero; nothing to boot");
        int n = Math.Min(floppyImage.Length, 0x10000 - 0x0100);
        Buffer.BlockCopy(floppyImage, 0, mem, 0x0100, n);
        PC = 0x0103;
        Halted = false;
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
        if (AnyHawkMounted && a >= 0xF140 && a <= 0xF148) return ReadHawkReg(a);
        if (a >= 0xF140 && a <= 0xF145) return ReadFloppyReg(a);
        if (a == 0xF800) return ffcResult;
        if (a == 0xF801) return ffcStatus;
        return mem[a];
    }
    void Write8(ushort a, int v)
    {
        byte b = (byte)v;
        if (a == 0xF200) return; // MUX0 control/config
        if (a == 0xF20A || a == 0xF20E) { muxInterruptEnabled = b != 0; mem[a] = b; return; } // MUX interrupt-ish enables used by WIPL
        if (a == 0xF201)
        {
            var h = TerminalOutput;
            if (h != null) h((char)b);
            else
            {
                int c = b;
                if (c >= 0x80) c &= 0x7F; // keep headless boot logs readable too
                if (c == '\r') return;
                if (c == '\b') { Console.Write("\b \b"); return; }
                if (c == '\f') Console.WriteLine();
                else Console.Write((char)c);
            }
            return;
        }
        if (AnyHawkMounted && a >= 0xF140 && a <= 0xF148) { WriteHawkReg(a, b); return; }
        if (a >= 0xF140 && a <= 0xF145) { WriteFloppyReg(a, b); return; }
        if (a == 0xF800) { WriteFfcCommand(b); return; }
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
        if (debugDepositActive || cedActive || keyTraceActive)
        {
            if (terminalInput.Count != 0)
            {
                byte b = terminalInput.Dequeue();
                if (debugDepositActive) DebugDepositKey(b);
                else if (cedActive) CedKey(b);
                else KeyTraceKey(b);
            }
            return;
        }
        ServiceInterrupts();
        ushort oldpc = PC; op = Fetch();
        if (Trace) Console.Error.WriteLine("{0:X4}: {1:X2} {2} AX={3:X4} BX={4:X4} RT={5:X4} DX={6:X4} EX={7:X4} SP={8:X4} GX={9:X4} HX={10:X4}", oldpc, op, FlagString(), RegPair(AX), RegPair(BX), RegPair(RT), RegPair(DX), RegPair(EX), RegPair(SP), RegPair(GX), RegPair(HX));
        if (op < 0x10) Low(); else if (op < 0x20) Branch(); else if (op < 0x30) Misc8(); else if (op < 0x40) Misc16(); else if (op < 0x50) Alu8(); else if (op < 0x60) Alu16(); else if (op == 0x66) Svc(); else if (op == 0x67) MemOp(); else if (op < 0x70) Rt(); else if (op < 0x80) Jump(); else LoadStore();
    }

    void ServiceInterrupts()
    {
        if ((flags & I) == 0) return;
        // Centurion MUX input is observed in WIPL as a level-6 interrupt.  The
        // boot code installs the level's entry PC in interlevel register P/HX
        // via SAR 6,P and then polls LAR 6,A for the character deposited by
        // the interrupt routine.
        if (!muxInterruptEnabled || terminalInput.Count == 0 || ipl >= 6) return;
        ushort vector = ReadInterLevelPair(6, HX);
        if (vector == 0 || ReadInterLevelPair(6, AX) != 0) return;
        interruptStack.Push(new InterruptFrame(ipl, PC, flags));
        ipl = 6;
        PC = vector;
        flags = (byte)(flags & unchecked((byte)~I));
        Halted = false;
    }

    void Low()
    {
        switch (op)
        {
            case 0x00: Halted = true; break; case 0x01: break;
            case 0x02: flags |= N; break; case 0x03: flags &= unchecked((byte)~N); break;
            case 0x04: flags |= I; break; case 0x05: flags &= unchecked((byte)~I); break;
            case 0x06: flags |= C; break; case 0x07: flags &= unchecked((byte)~C); break;
            case 0x08: flags = (byte)(flags ^ C); break;
            case 0x09: PC = RegPair(RT); SetRegPair(RT, Pop()); break;
            case 0x0A: ReturnInterrupt(restoreFlags: true); break;
            case 0x0B: ReturnInterrupt(restoreFlags: false); break;
            case 0x0D: SetRegPair(RT, PC); break;
            case 0x0E: break;
            case 0x0F: ReturnInterrupt(restoreFlags: true); break;
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
            case 6: t = (flags & N) != 0; break; // BM: branch on minus
            case 7: t = (flags & N) == 0; break; // BP: branch on plus
            case 8: t = (flags & (N | Z)) == 0; break; // BGZ: not minus and not zero
            case 9: t = (flags & (N | Z)) != 0; break; // BLE: less-or-equal zero
            case 14: t = (flags & I) != 0; break;
            case 15: t = false; break; // clock interrupt enable is not modelled yet
            default: t = false; break;
        }
        sbyte off = unchecked((sbyte)Fetch()); if (t) PC = (ushort)(PC + off);
    }

    void ReturnInterrupt(bool restoreFlags)
    {
        if (interruptStack.Count == 0) { if (op == 0x0F) ipl = 15; return; }
        InterruptFrame f = interruptStack.Pop();
        PC = f.Pc;
        ipl = f.Ipl;
        if (restoreFlags) flags = f.Flags;
        else flags |= I;
    }
    ushort Indexed(int size)
    {
        byte idx = Fetch();
        if ((idx & 0x10) != 0) Unknown();
        int r = (idx >> 4) >> 1;
        int transferSize = (idx & 4) != 0 ? 2 : size; // indirect forms point at word pointers
        ushort reg = RegPair(r);
        if ((idx & 3) == 2) reg = (ushort)(reg - transferSize);
        ushort a = reg;
        if ((idx & 3) == 1) reg = (ushort)(reg + transferSize);
        else if ((idx & 3) != 0 && (idx & 3) != 2) Unknown();
        SetRegPair(r, reg);
        if ((idx & 8) != 0) a = (ushort)(a + unchecked((sbyte)Fetch()));
        if ((idx & 4) != 0) a = Read16(a);
        return a;
    }
    ushort Addr(int size, int mode)
    {
        ushort a;
        switch (mode & 15)
        {
            case 0: a = PC; PC += (ushort)size; break;
            case 1: a = Fetch16(); break;
            case 2: a = Read16(Fetch16()); break;
            case 3: { sbyte off = unchecked((sbyte)Fetch()); a = (ushort)(PC + off); break; }
            case 4: { sbyte off = unchecked((sbyte)Fetch()); a = Read16((ushort)(PC + off)); break; }
            case 5: a = Indexed(size); break; default: a = RegPair(mode & 7); break;
        }
        return a;
    }
    void LoadStore()
    {
        if (op == 0xD7) { InterLevelStore(); return; }
        if (op == 0xE6) { InterLevelLoad(); return; }
        if (op == 0xF6) { Xio(); return; }
        int m = op & 15; bool b = (op & 0x40) != 0; ushort a; switch (op & 0x30) { case 0x00: a = Addr(1, m); Reg(b ? BL : AL, Read8(a)); Flag8(Reg(b ? BL : AL), false, 0); break; case 0x10: a = Addr(2, m); SetRegPair(b ? BX : AX, Read16(a)); Flag16(RegPair(b ? BX : AX), false, 0); break; case 0x20: a = Addr(1, m); Write8(a, Reg(b ? BL : AL)); break; case 0x30: a = Addr(2, m); Write16(a, RegPair(b ? BX : AX)); break; }
    }
    ushort InterLevelAddr(int level, int reg) { return (ushort)((level << 4) | (reg & 14)); }
    ushort InterLevelPairAddr(int level, int pair) { return InterLevelAddr(level, pair << 1); }
    ushort ReadInterLevelWord(int level, int reg) { ushort a = InterLevelAddr(level, reg); return (ushort)((Read8(a) << 8) | Read8((ushort)(a + 1))); }
    ushort ReadInterLevelPair(int level, int pair) { ushort a = InterLevelPairAddr(level, pair); return (ushort)((Read8(a) << 8) | Read8((ushort)(a + 1))); }
    void WriteInterLevelWord(int level, int reg, int v) { ushort a = InterLevelAddr(level, reg); Write8(a, v >> 8); Write8((ushort)(a + 1), v); }
    void InterLevelStore()
    {
        byte e = Fetch();
        int level = e >> 4, reg = e & 15;
        WriteInterLevelWord(level, reg, RegPair(AX));
    }
    void InterLevelLoad()
    {
        byte e = Fetch();
        int level = e >> 4, reg = e & 15;
        // Compatibility path for code that polls IL6(A) before it has enabled
        // the real interrupt path.
        if (e == 0x60 && ReadInterLevelPair(6, AX) == 0 && terminalInput.Count != 0 && ((flags & I) == 0 || ReadInterLevelPair(6, HX) == 0))
            WriteInterLevelWord(6, AX, terminalInput.Dequeue());
        SetRegPair(AX, ReadInterLevelWord(level, reg));
        Flag16(RegPair(AX), false, 0);
    }
    void Xio()
    {
        byte spec = Fetch();
        sbyte off = unchecked((sbyte)Fetch());
        ushort z = RegPair(EX);
        if (z == 0) z = (ushort)(0xF000 | RegPair(RT)); // Some HDIPL paths keep the Z/MMIO base as a low I/O page in RT.
        ushort a = (ushort)(z + off); // Z register is the device base in WIPL's XIO forms.
        if (spec == 0x19) Write8(a, Reg(AL));
        else if (spec == 0x39) Write8(a, Reg(BL));
        else if (spec == 0x18) { Reg(AL, Read8(a)); Flag8(Reg(AL), false, 0); }
        else if (spec == 0x38) { Reg(BL, Read8(a)); Flag8(Reg(BL), false, 0); }
        else Unknown();
    }
    void Rt() { ushort a = Addr(2, op & 7); if ((op & 8) != 0) Write16(a, RegPair(RT)); else SetRegPair(RT, Read16(a)); Flag16(RegPair(RT), false, 0); }
    void Svc()
    {
        byte svc = Fetch();
        if (svc == 0x40 && Read8(0x0806) == 0x71)
        {
            Push(RegPair(RT));
            SetRegPair(RT, PC);
            PC = 0x0806;
            return;
        }
        if (svc == 0x41) { DebugRegs(); return; }
        if (svc == 0x42) { DebugDump(ReadDebugAddress(0x0800)); return; }
        if (svc == 0x43) { DebugDisasm(ReadDebugAddress(0x0800)); return; }
        if (svc == 0x44) { StartDebugDeposit(ReadDebugAddress(0x0800)); return; }
        if (svc == 0x50) { StartCed(); return; }
        if (svc == 0x51) { TypeSystemMember(); return; }
        if (svc == 0x52) { CatalogSystem(); return; }
        if (svc == 0x53) { PrintCvitStatus(); return; }
        if (svc == 0x54) { StartKeyTrace(); return; }
        if (svc == 0x55) { PrefixCommand(); return; }
        if (svc == 0x56) { RunSystemMember(); return; }
        Unknown();
    }
    void DebugOut(string s) { foreach (char ch in s) Write8(0xF201, ch); }
    ushort ReadDebugAddress(ushort defaultAddr)
    {
        const ushort line = CommandLineBuffer;
        ushort addr = 0;
        int digits = 0;
        bool started = false;
        for (int i = 0; i < 8; i++)
        {
            byte ch = (byte)(mem[(ushort)(line + i)] & 0x7F);
            if (ch == '\r' || ch == '\n') break;
            if (!started && (ch == ' ' || ch == '\t')) continue;
            if (!started && ch == '$') { started = true; continue; }
            int v = HexValue(ch);
            if (v >= 0 && digits < 4)
            {
                started = true;
                addr = (ushort)((addr << 4) | v);
                digits++;
            }
        }
        return digits == 0 ? defaultAddr : addr;
    }
    int HexValue(byte ch)
    {
        if (ch >= '0' && ch <= '9') return ch - '0';
        if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
        if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
        return -1;
    }
    void StartKeyTrace()
    {
        keyTraceActive = true;
        DebugOut("\r\nKEY TRACE: press keys; ESC exits.\r\n");
    }
    void KeyTraceKey(byte raw)
    {
        byte ch = (byte)(raw & 0x7F);
        if (ch == 0x1B) { keyTraceActive = false; DebugOut("\r\nLEAVING KEY TRACE\r\n"); return; }
        string name = ch switch { 0x08 => "BS", 0x09 => "TAB", 0x0A => "LF", 0x0D => "CR", 0x7F => "DEL", _ => ch >= 32 && ch < 127 ? ((char)ch).ToString() : "CTRL" };
        DebugOut($"${ch:X2} {name}\r\n");
    }
    void StartDebugDeposit(ushort addr)
    {
        debugDepositActive = true;
        debugDepositAddr = addr;
        debugDepositInput.Clear();
        DebugOut("Use '.' to end.\r\n");
        DebugDepositPrompt();
    }
    void DebugDepositPrompt()
    {
        DebugOut($"{debugDepositAddr:X4}: {mem[debugDepositAddr]:X2} __\b\b");
    }
    void DebugDepositKey(byte raw)
    {
        byte ch = (byte)(raw & 0x7F);
        if (ch == '\n') return;
        if (ch == '\r')
        {
            string s = debugDepositInput.ToString().Trim();
            DebugOut("\r\n");
            if (s == ".") { debugDepositActive = false; return; }
            if (s.Length > 0)
            {
                int v = 0, digits = 0;
                foreach (char c in s)
                {
                    int h = HexValue((byte)c);
                    if (h < 0 || digits >= 2) { digits = -1; break; }
                    v = (v << 4) | h;
                    digits++;
                }
                if (digits > 0) { mem[debugDepositAddr] = (byte)v; debugDepositAddr++; }
                else DebugOut("?HEX\r\n");
            }
            debugDepositInput.Clear();
            DebugDepositPrompt();
            return;
        }
        if (ch == 0x08 || ch == 0x7F)
        {
            if (debugDepositInput.Length > 0) { debugDepositInput.Length--; DebugOut("\b_\b"); }
            return;
        }
        if (ch == '.' || HexValue(ch) >= 0)
        {
            if (debugDepositInput.Length < 2 || (ch == '.' && debugDepositInput.Length == 0))
            {
                debugDepositInput.Append((char)ch);
                Write8(0xF201, ch);
            }
        }
    }
    CvitFileSystem CvitFsForDevice(int unit) => unit == 0 ? (cvitFileSystems[0] ?? cvitFs) : cvitFileSystems[unit];
    (int Device, string Prefix, string Member, string Display) ParseCvitPath(string spec, string defaultMember, params string[] commandPrefixes)
    {
        string s = RemoveWhitespace(spec).ToUpperInvariant();
        foreach (string cmdPrefix in commandPrefixes)
            if (s.StartsWith(cmdPrefix, StringComparison.Ordinal)) { s = s.Substring(cmdPrefix.Length); break; }
        int dev = currentCvitDevice;
        int colon = s.IndexOf(':');
        if (colon >= 0)
        {
            string d = s.Substring(0, colon);
            if (d == "H0") dev = 0; else if (d == "H1") dev = 1;
            s = s.Substring(colon + 1);
        }
        string prefix = currentCvitPrefix;
        string member = defaultMember;
        if (s.Length != 0)
        {
            if (s.StartsWith("/", StringComparison.Ordinal))
            {
                int slash = s.LastIndexOf('/');
                prefix = slash <= 0 ? "/" : s.Substring(0, slash);
                member = slash == s.Length - 1 ? "" : s.Substring(slash + 1);
            }
            else if (s.Contains('/'))
            {
                int slash = s.LastIndexOf('/');
                prefix = "/" + s.Substring(0, slash);
                member = slash == s.Length - 1 ? "" : s.Substring(slash + 1);
            }
            else member = s;
        }
        if (member.Length > 10) member = member.Substring(0, 10);
        string display = $"H{dev}:{prefix}" + (String.IsNullOrEmpty(member) ? "" : "/" + member);
        return (dev, prefix, member, display);
    }
    bool IsSystemPrefix(string prefix) => String.Equals(prefix, "/SYSTEM", StringComparison.OrdinalIgnoreCase) || prefix == "/";
    void TypeSystemMember()
    {
        var parsed = ParseCvitPath(ReadDebugLine(), "WELCOME", "YPE", "TYPE");
        if (!IsSystemPrefix(parsed.Prefix)) { DebugOut("?NO LIBRARY\r\n"); return; }
        CvitFileSystem fs = CvitFsForDevice(parsed.Device);
        if (fs == null) { DebugOut("?NO HAWK\r\n"); return; }
        if (!fs.TryReadTextMember(parsed.Member, out string text)) { DebugOut("?NO FILE\r\n"); return; }
        DebugOut("\r\n");
        foreach (char ch in text) Write8(0xF201, ch);
        DebugOut("\r\n");
    }
    void RunSystemMember()
    {
        var parsed = ParseCvitPath(ReadDebugLine(), "", "UN", "RUN");
        if (String.IsNullOrEmpty(parsed.Member)) { DebugOut("?RUN WHAT\r\n"); return; }
        if (!IsSystemPrefix(parsed.Prefix)) { DebugOut("?NO LIBRARY\r\n"); return; }
        CvitFileSystem fs = CvitFsForDevice(parsed.Device);
        if (fs == null) { DebugOut("?NO HAWK\r\n"); return; }
        if (!fs.TryReadMember(parsed.Member, out byte[] data)) { DebugOut("?NO FILE\r\n"); return; }
        if (0x0100 + data.Length > mem.Length) { DebugOut("?TOO BIG\r\n"); return; }
        Array.Clear(mem, 0x0100, Math.Min(0x1000, mem.Length - 0x0100));
        Buffer.BlockCopy(data, 0, mem, 0x0100, data.Length);
        PC = 0x0100;
    }
    void CatalogSystem()
    {
        var parsed = ParseCvitPath(ReadDebugLine(), "", "ATALOG", "CATALOG", "AT", "CAT");
        if (!IsSystemPrefix(parsed.Prefix)) { DebugOut("\r\n?NO LIBRARY\r\n"); return; }
        CvitFileSystem fs = CvitFsForDevice(parsed.Device);
        if (fs == null) { DebugOut("?NO HAWK\r\n"); return; }
        if (!fs.LooksLikeSystemVolume()) { DebugOut("\r\n?NOT CVIT VOLUME\r\n"); return; }
        DebugOut("\r\nNAME       TYPE\r\n");
        foreach (var entry in fs.ListMembers())
            DebugOut($"{entry.Name.PadRight(10)} {entry.Type}\r\n");
    }
    void PrefixCommand()
    {
        string arg = ReadDebugLine();
        string s = RemoveWhitespace(arg).ToUpperInvariant();
        foreach (string prefix in new[] { "REFIX", "PREFIX" })
            if (s.StartsWith(prefix, StringComparison.Ordinal)) { s = s.Substring(prefix.Length); break; }
        if (s.Length == 0)
        {
            DebugOut($"\r\nH{currentCvitDevice}:{currentCvitPrefix}\r\n");
            return;
        }
        int dev = currentCvitDevice;
        int colon = s.IndexOf(':');
        if (colon >= 0)
        {
            string d = s.Substring(0, colon);
            if (d == "H0") dev = 0; else if (d == "H1") dev = 1;
            s = s.Substring(colon + 1);
        }
        if (s.Length == 0) s = currentCvitPrefix;
        if (!s.StartsWith("/", StringComparison.Ordinal)) s = "/" + s;
        currentCvitDevice = dev;
        currentCvitPrefix = s;
        DebugOut($"\r\nPREFIX H{currentCvitDevice}:{currentCvitPrefix}\r\n");
    }
    void PrintCvitStatus()
    {
        DebugOut("\r\nCPU6\r\n");
        DebugOut("MEM  128K\r\n\r\n");
        DebugOut("DISKS\r\n");
        DebugOut($" F0:  8\" FLOPPY   {(floppyImage == null ? "EMPTY" : "READY")}\r\n");
        DebugOut(" F1:  8\" FLOPPY   EMPTY\r\n");
        DebugOut(HawkStatusLine(0));
        DebugOut(HawkStatusLine(1));
        DebugOut("\r\nTERMINALS\r\n");
        DebugOut(" T0:  CONSOLE     9600\r\n");
        DebugOut(" T1:  MUX1        OFFLINE\r\n");
        DebugOut(" T2:  MUX2        OFFLINE\r\n");
        DebugOut(" T3:  MUX3        OFFLINE\r\n");
    }
    string HawkStatusLine(int unit)
    {
        if (unit < 0 || unit >= hawkImages.Length || hawkImages[unit] == null) return $" H{unit}:  HAWK        EMPTY\r\n";
        string kind = cvitFileSystems[unit] != null && cvitFileSystems[unit].LooksLikeSystemVolume() ? "CVIT" : "FOREIGN";
        return $" H{unit}:  HAWK        READY  {kind}\r\n";
    }
    void StartCed()
    {
        SetCedActiveFile(ReadDebugLine().Trim());
        CedLoadActiveFile();
        cedActive = true;
        cedInput.Clear();
        DebugOut("\r\nSYSTEM.CED V0.1\r\n");
        DebugOut($"ProDOS paths; active file {cedActiveDisplay}; DISPLAY defaults to current terminal. Q exits.\r\n");
        CedPrompt();
    }
    string ReadDebugLine()
    {
        const ushort line = CommandLineBuffer;
        var s = new StringBuilder();
        for (int i = 0; i < 32; i++)
        {
            byte ch = (byte)(mem[(ushort)(line + i)] & 0x7F);
            if (ch == '\r' || ch == '\n') break;
            s.Append((char)ch);
        }
        return s.ToString();
    }
    void SetCedActiveFile(string spec)
    {
        var parsed = ParseCvitPath(spec, "TEST", "ED", "CED");
        cedActiveFile = parsed.Member;
        cedActiveDisplay = parsed.Display;
    }
    void CedPrompt() { DebugOut("CED:"); }
    void CedKey(byte raw)
    {
        byte ch = (byte)(raw & 0x7F);
        if (ch == '\n') return;
        if (ch == '\r')
        {
            string line = cedInput.ToString();
            cedInput.Clear();
            DebugOut("\r\n");
            CedCommand(line);
            if (cedActive) CedPrompt();
            return;
        }
        if (ch == 0x08 || ch == 0x7F)
        {
            if (cedInput.Length > 0) { cedInput.Length--; DebugOut("\b \b"); }
            return;
        }
        if (ch >= 32 && ch < 127)
        {
            cedInput.Append((char)ch);
            Write8(0xF201, ch);
        }
    }
    void CedCommand(string input)
    {
        string trimmed = input.Trim();
        string compact = RemoveWhitespace(trimmed).ToUpperInvariant();
        if (compact.Length == 0) return;
        if (compact == "Q" || compact == "QUIT" || compact == "EXIT") { cedActive = false; DebugOut("LEAVING CED\r\n"); return; }
        if (compact == "HELP" || compact == "?") { DebugOut("Pfirst,last print; W writes active file; DISPLAY uses current terminal; n text sets line; Q quits\r\n"); return; }
        if (compact == "DISPLAY") { DebugOut("DISPLAY T0\r\n"); return; }
        if (compact == "W" || compact == "WRITE") { CedWriteActiveFile(); return; }
        if (compact.StartsWith("WRITE", StringComparison.Ordinal) && compact.Length > 5) { SetCedActiveFile(compact.Substring(5)); CedWriteActiveFile(); return; }
        if (compact[0] == 'W' && compact.Length > 1) { SetCedActiveFile(compact.Substring(1)); CedWriteActiveFile(); return; }
        if (compact[0] == 'P') { CedPrint(compact.Substring(1)); return; }
        if (compact.EndsWith("P", StringComparison.Ordinal) && compact.Length > 1) { CedPrint(compact.Substring(0, compact.Length - 1)); return; }
        if (Char.IsDigit(trimmed[0])) { CedSetLine(trimmed); return; }
        DebugOut("?CED\r\n");
    }
    string RemoveWhitespace(string s)
    {
        var b = new StringBuilder();
        foreach (char c in s) if (!Char.IsWhiteSpace(c)) b.Append(c);
        return b.ToString();
    }
    bool ParseNumber(string s, ref int i, out int n)
    {
        n = 0; int start = i;
        while (i < s.Length && Char.IsDigit(s[i])) { n = n * 10 + (s[i] - '0'); i++; }
        return i != start;
    }
    void CedPrint(string spec)
    {
        int i = 0;
        if (!ParseNumber(spec, ref i, out int first)) { DebugOut("?RANGE\r\n"); return; }
        int last = first;
        if (i < spec.Length && spec[i] == ',') { i++; if (!ParseNumber(spec, ref i, out last)) last = first; }
        foreach (var kv in cedLines)
            if (kv.Key >= first && kv.Key <= last) DebugOut($"{kv.Key,5} {kv.Value}\r\n");
    }
    void CedSetLine(string input)
    {
        int i = 0;
        if (!ParseNumber(input, ref i, out int n)) { DebugOut("?LINE\r\n"); return; }
        string text = i < input.Length ? input.Substring(i).TrimStart() : "";
        if (text.Length == 0) cedLines.Remove(n);
        else cedLines[n] = text;
    }
    void CedLoadActiveFile()
    {
        cedLines.Clear();
        var path = ParseCvitPath(cedActiveDisplay, cedActiveFile);
        if (!IsSystemPrefix(path.Prefix)) return;
        CvitFileSystem fs = CvitFsForDevice(path.Device);
        if (fs == null || !fs.TryReadTextMember(cedActiveFile, out string text)) return;
        int lineNo = 1;
        var line = new StringBuilder();
        for (int i = 0; i < text.Length; i++)
        {
            char ch = text[i];
            if (ch == '\r' || ch == '\n')
            {
                if (line.Length != 0) cedLines[lineNo] = line.ToString();
                lineNo++;
                line.Clear();
                if (ch == '\r' && i + 1 < text.Length && text[i + 1] == '\n') i++;
            }
            else if (ch >= 32 && ch < 127) line.Append(ch);
        }
        if (line.Length != 0) cedLines[lineNo] = line.ToString();
    }
    void CedWriteActiveFile()
    {
        var path = ParseCvitPath(cedActiveDisplay, cedActiveFile);
        if (!IsSystemPrefix(path.Prefix)) { DebugOut("?NO LIBRARY\r\n"); return; }
        CvitFileSystem fs = CvitFsForDevice(path.Device);
        if (fs == null) { DebugOut("?NO HAWK\r\n"); return; }
        var text = new StringBuilder();
        foreach (var kv in cedLines) text.Append(kv.Value).Append("\r\n");
        if (!fs.WriteTextMember(cedActiveFile, text.ToString(), createIfMissing: true, out string error)) { DebugOut(error + "\r\n"); return; }
        DebugOut($"Wrote {cedActiveDisplay}\r\n");
    }
    void DebugRegs()
    {
        DebugOut($"PC={PC:X4} FLAGS={FlagString(),-4} IPL={ipl:X1} AX={RegPair(AX):X4} BX={RegPair(BX):X4} RT={RegPair(RT):X4} DX={RegPair(DX):X4}\r\n");
        DebugOut($"EX={RegPair(EX):X4} SP={RegPair(SP):X4} GX={RegPair(GX):X4} HX={RegPair(HX):X4}\r\n");
    }
    void DebugDump(ushort a)
    {
        for (int row = 0; row < 4; row++)
        {
            ushort baseAddr = (ushort)(a + row * 16);
            var sb = new StringBuilder();
            sb.Append($"{baseAddr:X4}:");
            for (int i = 0; i < 16; i++) sb.Append($" {mem[(ushort)(baseAddr + i)]:X2}");
            sb.Append("  ");
            for (int i = 0; i < 16; i++) { byte b = mem[(ushort)(baseAddr + i)]; sb.Append(b >= 32 && b < 127 ? (char)b : '.'); }
            sb.Append("\r\n");
            DebugOut(sb.ToString());
        }
    }
    void DebugDisasm(ushort a)
    {
        for (int i = 0; i < 8; i++)
        {
            string text = MiniDisasm(a, out int len);
            DebugOut(text + "\r\n");
            a = (ushort)(a + len);
        }
    }
    string MiniDisasm(ushort pc, out int len)
    {
        byte op = mem[pc], b1 = mem[(ushort)(pc + 1)], b2 = mem[(ushort)(pc + 2)];
        len = 1;
        switch (op)
        {
            case 0x00: return $"{pc:X4}: 00       HLT";
            case 0x01: return $"{pc:X4}: 01       NOP";
            case 0x09: return $"{pc:X4}: 09       RSR";
            case 0x66: len = 2; return $"{pc:X4}: 66 {b1:X2}    SVC ${b1:X2}";
            case 0x71: len = 3; return $"{pc:X4}: 71 {b1:X2} {b2:X2} JMP ${((b1 << 8) | b2):X4}";
            case 0x79: len = 3; return $"{pc:X4}: 79 {b1:X2} {b2:X2} JSR ${((b1 << 8) | b2):X4}";
            case 0x80: len = 2; return $"{pc:X4}: 80 {b1:X2}    LDAB #${b1:X2}";
            case 0x81: len = 3; return $"{pc:X4}: 81 {b1:X2} {b2:X2} LDAB ${((b1 << 8) | b2):X4}";
            case 0x90: len = 3; return $"{pc:X4}: 90 {b1:X2} {b2:X2} LDA #${((b1 << 8) | b2):X4}";
            case 0x91: len = 3; return $"{pc:X4}: 91 {b1:X2} {b2:X2} LDA ${((b1 << 8) | b2):X4}";
            case 0xA1: len = 3; return $"{pc:X4}: A1 {b1:X2} {b2:X2} STAB ${((b1 << 8) | b2):X4}";
            case 0xB1: len = 3; return $"{pc:X4}: B1 {b1:X2} {b2:X2} STA ${((b1 << 8) | b2):X4}";
            case 0xC0: len = 2; return $"{pc:X4}: C0 {b1:X2}    LDBB #${b1:X2}";
            case 0xD0: len = 3; return $"{pc:X4}: D0 {b1:X2} {b2:X2} LDB #${((b1 << 8) | b2):X4}";
            case 0xE1: len = 3; return $"{pc:X4}: E1 {b1:X2} {b2:X2} STBB ${((b1 << 8) | b2):X4}";
            case 0xF1: len = 3; return $"{pc:X4}: F1 {b1:X2} {b2:X2} STB ${((b1 << 8) | b2):X4}";
            default: return $"{pc:X4}: {op:X2}       DB ${op:X2}";
        }
    }
    void Jump()
    {
        if (op == 0x7E) { PushBytes(); return; }
        if (op == 0x7F) { PopBytes(); return; }
        ushort n; switch (op & 7) { case 0: n = RegPair(AX); break; case 1: n = Fetch16(); break; case 2: n = Read16(Fetch16()); break; case 3: { sbyte off = unchecked((sbyte)Fetch()); n = (ushort)(PC + off); break; } case 4: { sbyte off = unchecked((sbyte)Fetch()); n = Read16((ushort)(PC + off)); break; } case 5: n = Indexed(2); break; default: Unknown(); return; }
        if ((op & 8) != 0) { Push(RegPair(RT)); SetRegPair(RT, PC); } PC = n;
    }
    void PushBytes()
    {
        byte e = Fetch();
        int r = e >> 4, count = (e & 15) + 1;
        ushort sp = RegPair(SP);
        r += count;
        while (count-- > 0) { sp--; r--; Write8(sp, Reg(r & 15)); }
        SetRegPair(SP, sp);
    }
    void PopBytes()
    {
        byte e = Fetch();
        int r = e >> 4, count = (e & 15) + 1;
        ushort sp = RegPair(SP);
        while (count-- > 0) { Reg(r & 15, Read8(sp)); sp++; r++; }
        SetRegPair(SP, sp);
    }
    void Misc8()
    {
        int r = AL, count = 1; if ((op & 8) == 0) { byte enc = Fetch(); if ((enc & 15) != 0) { if (op == 0x22 && enc == 0x32) flags |= Z; else if (op == 0x20 || op == 0x21 || (op >= 0x24 && op <= 0x27)) { r = enc >> 4; count = (enc & 15) + 1; } else { Unknown(); return; } } else r = enc >> 4; }
        switch (op) { case 0x20: while (count-- > 0) Inc8(r); break; case 0x21: while (count-- > 0) Dec8(r); break; case 0x22: Reg(r, 0); Flag8(0, false, 0); break; case 0x23: Reg(r, ~Reg(r)); Flag8(Reg(r), false, 0); break; case 0x24: while (count-- > 0) Shr8(r); break; case 0x25: while (count-- > 0) Shl8(r); break; case 0x26: while (count-- > 0) Rrc8(r); break; case 0x27: while (count-- > 0) Rlc8(r); break; case 0x28: Inc8(AL); break; case 0x29: Dec8(AL); break; case 0x2A: Reg(AL, 0); Flag8(0, false, 0); break; case 0x2B: Reg(AL, ~Reg(AL)); Flag8(Reg(AL), false, 0); break; case 0x2C: Shr8(AL); break; case 0x2D: Shl8(AL); break; case 0x2E: byte e = Fetch(); SetRegPair((e & 15) >> 1, (ushort)(e >> 5)); break; case 0x2F: Dma(); break; default: Unknown(); break; }
    }
    void Misc16()
    {
        int r = AX, count = 1; if ((op & 8) == 0) { byte enc = Fetch(); if ((enc & 15) != 0) { if (op == 0x22 && enc == 0x32) flags |= Z; else if (op == 0x33) r = (enc >> 4) >> 1; else if (op == 0x30 || op == 0x31 || (op >= 0x34 && op <= 0x37)) { r = (enc >> 4) >> 1; count = (enc & 15) + 1; } else { Unknown(); return; } } else r = enc >> 5; }
        switch (op) { case 0x30: while (count-- > 0) Inc16(r); break; case 0x31: while (count-- > 0) Dec16(r); break; case 0x32: SetRegPair(r, 0); Flag16(0, false, 0); break; case 0x33: SetRegPair(r, (ushort)~RegPair(r)); Flag16(RegPair(r), false, 0); break; case 0x34: while (count-- > 0) Shr16(r); break; case 0x35: while (count-- > 0) Shl16(r); break; case 0x36: while (count-- > 0) Rrc16(r); break; case 0x37: while (count-- > 0) Rlc16(r); break; case 0x38: Inc16(AX); break; case 0x39: Dec16(AX); break; case 0x3A: SetRegPair(AX, 0); Flag16(0, false, 0); break; case 0x3B: SetRegPair(AX, (ushort)~RegPair(AX)); Flag16(RegPair(AX), false, 0); break; case 0x3C: Shr16(AX); break; case 0x3D: Shl16(AX); break; case 0x3E: Inc16(RT); break; case 0x3F: Dec16(RT); break; }
    }
    void Alu8()
    {
        if (op == 0x46) { BigNum(); return; }
        if (op == 0x47) { MemOp(); return; }
        int s = AL, d = BL;
        if ((op & 8) == 0) { byte e = Fetch(); s = e >> 4; d = e & 15; }
        else if (op >= 0x4B)
        {
            d = op == 0x4B ? RL : op == 0x4C ? DL : op == 0x4D ? BL : op == 0x4E ? EL : SL;
            Reg(d, Reg(s)); Flag8(Reg(d), false, 0); return;
        }
        switch (op & 7) { case 0: Add8(d, s); break; case 1: Sub8(d, s); break; case 2: And8(d, s); break; case 3: Or8(d, s); break; case 4: Xor8(d, s); break; case 5: Reg(d, Reg(s)); Flag8(Reg(d), false, 0); break; default: Unknown(); break; }
    }
    void Alu16()
    {
        int s = AX, d = BX;
        bool extended = false;
        ushort src = 0, dst = 0;
        if ((op & 8) == 0)
        {
            byte e = Fetch();
            int mode = e & 0x11;
            s = (e >> 4) >> 1;
            d = (e & 15) >> 1;
            if (mode != 0)
            {
                ushort a = PC; PC += 2;
                if ((mode & 1) != 0) a = Read16(a);
                if (mode == 0x11) { a = (ushort)(a + RegPair(s)); s = d; }
                src = Read16(a);
                dst = RegPair(s);
                extended = true;
            }
        }
        else if (op >= 0x5B)
        {
            d = op == 0x5B ? RT : op == 0x5C ? DX : op == 0x5D ? BX : op == 0x5E ? EX : SP;
            SetRegPair(d, RegPair(s)); Flag16(RegPair(d), false, 0); return;
        }
        if (!extended) { src = RegPair(s); dst = RegPair(d); }
        ushort result;
        switch (op & 7)
        {
            case 0: { int r = dst + src; result = (ushort)r; SetRegPair(d, result); Flag16(r, true, r > 0xFFFF ? 1 : 0); break; }
            case 1: { int r = src - dst; result = (ushort)r; SetRegPair(d, result); Flag16(r, true, r >= 0 ? 1 : 0); break; } // dst = src - dst; L set when no borrow
            case 2: result = (ushort)(dst & src); SetRegPair(d, result); Flag16(result, false, 0); break;
            case 3: result = (ushort)(dst | src); SetRegPair(d, result); Flag16(result, false, 0); break;
            case 4: result = (ushort)(dst ^ src); SetRegPair(d, result); Flag16(result, false, 0); break;
            case 5: SetRegPair(d, src); Flag16(src, false, 0); break;
            default: Unknown(); break;
        }
    }
    ushort ExtendedOperandAddress(int mode)
    {
        switch (mode & 3)
        {
            case 0: return Fetch16();
            case 1:
            {
                byte regs = Fetch();
                int r1 = (regs >> 4) >> 1, r2 = (regs & 15) >> 1;
                int disp = (regs & 0x10) != 0 ? Fetch16() : unchecked((sbyte)Fetch());
                return (ushort)(disp + RegPair(r1) + (r2 == AX ? 0 : RegPair(r2)));
            }
            case 2: return RegPair((Fetch() & 15) >> 1);
            case 3: return PC;
            default: return 0;
        }
    }

    int ReadBigInt(ushort a, int bytes)
    {
        if (bytes <= 0) bytes = 2;
        int v = 0;
        for (int i = 0; i < bytes; i++) v = (v << 8) | Read8((ushort)(a + i));
        int signBit = 1 << Math.Min(30, bytes * 8 - 1);
        if (bytes < 4 && (v & signBit) != 0) v -= 1 << (bytes * 8);
        return v;
    }

    void BigNum()
    {
        byte spec = Fetch();
        int selector = spec >> 4, m = (spec >> 2) & 3, n = spec & 3;
        ushort op1 = ExtendedOperandAddress(m), op2 = ExtendedOperandAddress(n);
        if (selector == 8) // CTB/IBASECONV: base string to big number.
        {
            int b = (Read8(op1) & 0x7F) + 2;
            if (b < 2 || b > 36) b = 10;
            int value = 0;
            ushort p = (ushort)(op1 + 1);
            while (p != 0)
            {
                int ch = Read8(p) & 0x7F;
                int digit = ch >= '0' && ch <= '9' ? ch - '0' : ch >= 'A' && ch <= 'Z' ? ch - 'A' + 10 : -1;
                if (digit < 0 || digit >= b) break;
                value = value * b + digit;
                p++;
            }
            Write16(op2, value);
            Write16((ushort)(op2 + 2), 0);
            SetRegPair(AX, p);
            Flag16(value, false, 0);
            return;
        }
        if (selector == 9) // CFB/OBASECONV: big number to formatted base string.
        {
            int len = Reg(AL);
            if (len <= 0) len = 1;
            int b = (Read8(op1) & 0x7F) + 2;
            if (b < 2 || b > 36) b = 10;
            int value = ReadBigInt(op2, Math.Min(4, Math.Max(1, len)));
            string digits = Convert.ToString(Math.Abs(value), b).ToUpperInvariant();
            if (value < 0) digits = "-" + digits;
            byte pad = Reg(BL);
            if (pad == 0 || pad == 0xFF) pad = 0xA0;
            for (int i = 0; i < len; i++) Write8((ushort)(op1 + i), pad);
            int start = Math.Max(0, len - digits.Length);
            for (int i = 0; i < digits.Length && start + i < len; i++) Write8((ushort)(op1 + start + i), digits[i] | 0x80);
            SetRegPair(AX, (ushort)(op1 + len));
            Flag16(value, false, 0);
            return;
        }
        throw new InvalidOperationException($"unsupported bignum selector {selector:X} modes={m},{n} at ${(ushort)(PC - 1):X4}");
    }

    void MemOp()
    {
        byte ib = Fetch();
        if (op == 0x67)
        {
            byte spec = Fetch();
            if (ib == 0x4A && spec == 0x86)
            {
                // Variable-length memcpy used by WIPL/FDIPL's object loader:
                //   67 4A 86  memcpy AL+1, [EX/Z], [DX/Y]
                // The loader preloads AL with length-1 and expects X/Y/Z to be
                // preserved so it can advance pointers itself afterwards.
                int vlen = Reg(AL) + 1;
                ushort src = RegPair(EX), dst = RegPair(DX);
                for (int i = 0; i < vlen; i++) Write8((ushort)(dst + i), Read8((ushort)(src + i)));
                return;
            }
            Unknown();
            return;
        }

        int selector = ib >> 4;
        int len = Fetch() + 1;
        if (selector == 4 || selector == 9)
        {
            byte value = Fetch();
            ushort dst = Fetch16();
            for (int i = 0; i < len; i++) Write8((ushort)(dst + i), value);
            Flag8(value, false, 0);
            return;
        }
        Unknown();
    }

    void Dma()
    {
        byte e = Fetch();
        int hi = e >> 4;
        int rp = hi >> 1; // DMA register operands use byte-register encoding: 0=A, A=S, etc.
        switch (e & 15)
        {
            case 0: dmaAddr = RegPair(rp); break;
            case 1: SetRegPair(rp, dmaAddr); break;
            case 2: dmaCount = RegPair(rp); break;
            case 3: SetRegPair(rp, dmaCount); break;
            case 4: dmaMode = (byte)hi; break;
            case 6: break;
            default: Unknown(); break;
        }
    }

    byte ReadHawkReg(ushort a)
    {
        switch (a - 0xF140)
        {
            case 0: return (byte)(0xF0 | (hawkUnit & 0x0F));
            case 1: return (byte)(hawkSectorAddress >> 8);
            case 2: return (byte)hawkSectorAddress;
            case 3: return hawkWriteMask;
            case 4: return hawkStatus;
            case 5: return hawkDriveStatus;
            case 8: return hawkCommand;
            default: return 0;
        }
    }
    void WriteHawkReg(ushort a, byte v)
    {
        switch (a - 0xF140)
        {
            case 0: hawkUnit = v; break;
            case 1: hawkSectorAddress = (ushort)((hawkSectorAddress & 0x00FF) | (v << 8)); break;
            case 2: hawkSectorAddress = (ushort)((hawkSectorAddress & 0xFF00) | v); break;
            case 3: hawkWriteMask = v; break;
            case 4: hawkStatus = v; break;
            case 5: hawkDriveStatus = v; break;
            case 8: hawkCommand = v; ExecuteHawkCommand(v); break;
        }
    }
    void ExecuteHawkCommand(byte cmd)
    {
        EnsureHawk();
        hawkStatus = 0;
        hawkDriveStatus = 0x30;
        try
        {
            switch (cmd)
            {
                case 0: HawkTransfer(read: true); break;
                case 1: HawkTransfer(read: false); break;
                case 2: break; // seek: address register already names the target sector
                case 3: hawkSectorAddress = 0; break; // return to zero
                case 4: break; // verify read
                case 5:
                case 6: break; // format steps: acknowledge only
                default: throw new InvalidOperationException("bad Hawk command");
            }
            hawkStatus = 0;
            hawkDriveStatus = 0x3F;
        }
        catch
        {
            hawkStatus = 0x80;
            hawkDriveStatus = 0x10;
            throw;
        }
    }
    int HawkLogicalSectorForAddress()
    {
        int cylinder = (hawkSectorAddress >> 5) & 0x7FF;
        int head = (hawkSectorAddress >> 4) & 1;
        int sector = hawkSectorAddress & 0x0F;
        return ((cylinder * HawkHeads) + head) * HawkSectorsPerTrack + sector;
    }
    int HawkImageOffsetForLogicalSector(int logicalSector) => HawkImageOffset + logicalSector * HawkSectorStride;
    void HawkTransfer(bool read)
    {
        int unit = ActiveHawkUnit;
        byte[] image = ActiveHawkImage();
        int logicalSector = HawkLogicalSectorForAddress();
        int imageOffset = HawkImageOffsetForLogicalSector(logicalSector);
        int count = DmaTransferCount();
        if (count <= 0) count = HawkSectorSize;
        if (dmaAddr + count > 65536) throw new InvalidOperationException("Hawk DMA transfer crosses memory end");
        if (FloppyTrace)
        {
            int cylinder = (hawkSectorAddress >> 5) & 0x7FF, head = (hawkSectorAddress >> 4) & 1, sector = hawkSectorAddress & 0x0F;
            string first16 = read && imageOffset >= 0 && imageOffset < image.Length ? BitConverter.ToString(image, imageOffset, Math.Min(16, Math.Min(HawkSectorSize, image.Length - imageOffset))).Replace("-", " ") : "";
            Console.Error.WriteLine($"Hawk {(read ? "READ" : "WRITE")} unit={unit} cyl={cylinder} head={head} sector={sector} addr=${hawkSectorAddress:X4} bytes={count} dma=${dmaAddr:X4} raw_offset={imageOffset} stride={HawkSectorStride} first16={first16}");
        }
        int remaining = count, done = 0;
        while (remaining > 0)
        {
            int n = Math.Min(HawkSectorSize, remaining);
            int off = HawkImageOffsetForLogicalSector(logicalSector++);
            if (off < 0 || off + n > image.Length) throw new InvalidOperationException($"Hawk address out of range: unit={unit} addr=${hawkSectorAddress:X4} offset={off} count={n}");
            if (read) Buffer.BlockCopy(image, off, mem, dmaAddr + done, n);
            else Buffer.BlockCopy(mem, dmaAddr + done, image, off, n);
            done += n;
            remaining -= n;
        }
        if (!read) SaveHawk(unit);
    }

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

    void WriteFfcCommand(byte cmd)
    {
        ffcCommand = cmd; ffcStatus = 0; ffcResult = 0;
        try
        {
            switch (cmd)
            {
                case 0x43: FfcLoadCommandBuffer(); break; // DMA command bytes from CPU to FFC
                case 0x45:
                    FfcExecuteCommandBuffer();
                    break; // execute buffered disk command, DMA data
                default: ffcResult = 0x80; break;
            }
        }
        catch
        {
            ffcResult = 0x80;
            throw;
        }
        finally { ffcStatus = 1; }
    }

    int DmaTransferCount()
    {
        // Centurion boot code programs DMA count as one's-complement-ish FFFF-n;
        // the hardware transfers 0xFFFF-count bytes for these IPL paths.
        return dmaCount >= 0x8000 ? 0xFFFF - dmaCount : dmaCount;
    }

    void FfcLoadCommandBuffer()
    {
        int count = DmaTransferCount();
        if (count <= 0) count = 1;
        if (dmaAddr + count > 65536) throw new InvalidOperationException("FFC command DMA crosses memory end");
        ffcCommandBuffer = new byte[count];
        Buffer.BlockCopy(mem, dmaAddr, ffcCommandBuffer, 0, count);
        if (FloppyTrace) Console.Error.WriteLine($"FFC CMDBUF dma=${dmaAddr:X4} count={count} bytes={BitConverter.ToString(ffcCommandBuffer).Replace("-", " ")}");
    }

    void FfcExecuteCommandBuffer()
    {
        EnsureFloppy();
        int unit = 0, track = 0, head = 0, sector = 0, bytes = DmaTransferCount();
        bool read = false, write = false;
        for (int i = 0; i < ffcCommandBuffer.Length; )
        {
            byte c = ffcCommandBuffer[i++];
            if (c == 0xFF) break;
            switch (c)
            {
                case 0x81: if (i < ffcCommandBuffer.Length) unit = ffcCommandBuffer[i++]; break;
                case 0x83: if (i < ffcCommandBuffer.Length) track = ffcCommandBuffer[i++]; break;
                case 0x85: if (i < ffcCommandBuffer.Length) head = ffcCommandBuffer[i++]; break;
                case 0x88: read = true; if (i < ffcCommandBuffer.Length) sector = ffcCommandBuffer[i++]; if (i < ffcCommandBuffer.Length) i++; if (i + 1 < ffcCommandBuffer.Length) { bytes = (ffcCommandBuffer[i++] << 8) | ffcCommandBuffer[i++]; } break;
                case 0x89: write = true; if (i < ffcCommandBuffer.Length) sector = ffcCommandBuffer[i++]; if (i < ffcCommandBuffer.Length) i++; if (i + 1 < ffcCommandBuffer.Length) { bytes = (ffcCommandBuffer[i++] << 8) | ffcCommandBuffer[i++]; } break;
                default: break;
            }
        }
        if (!read && !write) { ffcResult = 0x40; return; }
        if (bytes <= 0) bytes = DmaTransferCount();
        int logicalSector;
        int imageOffset;
        if (FfcLinear)
        {
            // Experimental hard-disk/Hawk-style interpretation.  Normal FFC
            // floppy commands use track/sector addressing in the else branch.
            logicalSector = ((track & 0xff) << 8) | (sector & 0xff);
            imageOffset = logicalSector * FloppySectorSize;
            int maxSectors = FloppyTracks * FloppyHeads * FloppySectorsPerTrack;
            if (head < 0 || head >= FloppyHeads || logicalSector < 0 || logicalSector >= maxSectors) throw new InvalidOperationException($"FFC floppy address out of range: unit={unit} addr=${logicalSector:X4} hi={track} head={head} lo={sector} geometry={FloppyTracks}T/{FloppyHeads}H/{FloppySectorsPerTrack}S");
        }
        else
        {
            logicalSector = sector;
            imageOffset = (((track * FloppyHeads) + head) * FloppySectorsPerTrack + logicalSector) * FloppySectorSize;
            if (track < 0 || track >= FloppyTracks || head < 0 || head >= FloppyHeads || logicalSector < 0 || logicalSector >= FloppySectorsPerTrack) throw new InvalidOperationException($"FFC floppy address out of range: unit={unit} track={track} head={head} sector={sector} geometry={FloppyTracks}T/{FloppyHeads}H/{FloppySectorsPerTrack}S");
        }
        if (imageOffset + bytes > floppyImage.Length) bytes = Math.Max(0, floppyImage.Length - imageOffset);
        if (dmaAddr + bytes > 65536) throw new InvalidOperationException("FFC data DMA crosses memory end");
        if (FloppyTrace)
        {
            int peek = Math.Min(16, Math.Max(0, Math.Min(bytes, floppyImage.Length - imageOffset)));
            string first16 = read && peek > 0 ? BitConverter.ToString(floppyImage, imageOffset, peek).Replace("-", " ") : "";
            string addr = FfcLinear
                ? $"addr=${logicalSector:X4} hi={track:D2} lo={sector:D2}"
                : $"track={track:D2} head={head} sector={sector:D2} disk6=${(track * FloppySectorsPerTrack + sector):X4}";
            Console.Error.WriteLine($"FFC {(read ? "READ" : "WRITE")} unit={unit} {addr} bytes={bytes} dma=${dmaAddr:X4} raw_offset={imageOffset} first16={first16}");
        }
        if (read) Buffer.BlockCopy(floppyImage, imageOffset, mem, dmaAddr, bytes);
        else { Buffer.BlockCopy(mem, dmaAddr, floppyImage, imageOffset, bytes); SaveFloppy(); }
        floppyUnit = (byte)unit; floppyTrack = (byte)track; floppySector = (byte)sector; floppyHead = (byte)head; floppyStatus = 1;
        ffcResult = 0;
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
    bool AnyHawkMounted => hawkImages[0] != null || hawkImages[1] != null;
    int ActiveHawkUnit => (hawkUnit & 0x0F) == 1 ? 1 : 0;
    byte[] ActiveHawkImage()
    {
        int unit = ActiveHawkUnit;
        if (hawkImages[unit] == null) throw new InvalidOperationException($"no Hawk H{unit} mounted; use --hawk{unit} image");
        return hawkImages[unit];
    }
    CvitFileSystem ActiveCvitFs => cvitFileSystems[ActiveHawkUnit] ?? cvitFs;
    void EnsureHawk()
    {
        ActiveHawkImage();
    }
    void SaveFloppy()
    {
        if (String.IsNullOrEmpty(floppyPath)) return;
        File.WriteAllBytes(floppyPath, floppyImage);
    }
    void SaveHawk() => SaveHawk(0);
    void SaveHawk(int unit)
    {
        if (unit < 0 || unit >= hawkImages.Length || String.IsNullOrEmpty(hawkPaths[unit]) || hawkImages[unit] == null) return;
        File.WriteAllBytes(hawkPaths[unit], hawkImages[unit]);
    }
    static bool IsAllZero(byte[] bytes)
    {
        if (bytes == null || bytes.Length == 0) return true;
        for (int i = 0; i < bytes.Length; i++) if (bytes[i] != 0) return false;
        return true;
    }

    void Inc8(int r) { int v = Reg(r) + 1; Reg(r, v); Flag8(v, false, 0); } void Dec8(int r) { int v = Reg(r) - 1; Reg(r, v); Flag8(v, false, 0); }
    void Add8(int d, int s) { int v = Reg(d) + Reg(s); Reg(d, v); Flag8(v, true, v & 0x100); } void Sub8(int d, int s) { int v = Reg(s) - Reg(d); Reg(d, v); Flag8(v, true, v >= 0 ? 1 : 0); } // dst = src - dst; L set when no borrow
    void And8(int d, int s) { int v = Reg(d) & Reg(s); Reg(d, v); Flag8(v, true, 0); } void Or8(int d, int s) { int v = Reg(d) | Reg(s); Reg(d, v); Flag8(v, true, 0); } void Xor8(int d, int s) { int v = Reg(d) ^ Reg(s); Reg(d, v); Flag8(v, true, 0); }
    void Shl8(int r) { int v = Reg(r); Reg(r, v << 1); Flag8(v << 1, true, v & 0x80); } void Shr8(int r) { int v = Reg(r); Reg(r, v >> 1); Flag8(v >> 1, true, v & 1); } void Rlc8(int r) { int v = Reg(r); int c = v & 0x80; v = ((v << 1) | ((flags & C) != 0 ? 1 : 0)) & 0xFF; Reg(r, v); Flag8(v, true, c); } void Rrc8(int r) { int v = Reg(r); int c = v & 1; v = (v >> 1) | ((flags & C) != 0 ? 0x80 : 0); Reg(r, v); Flag8(v, true, c); }
    void Inc16(int r) { int v = RegPair(r) + 1; SetRegPair(r, (ushort)v); Flag16(v, false, 0); } void Dec16(int r) { int v = RegPair(r) - 1; SetRegPair(r, (ushort)v); Flag16(v, false, 0); }
    void Add16(int d, int s) { int v = RegPair(d) + RegPair(s); SetRegPair(d, (ushort)v); Flag16(v, true, v & 0x10000); } void Sub16(int d, int s) { int v = RegPair(s) - RegPair(d); SetRegPair(d, (ushort)v); Flag16(v, true, v >= 0 ? 1 : 0); }
    void And16(int d, int s) { int v = RegPair(d) & RegPair(s); SetRegPair(d, (ushort)v); Flag16(v, true, 0); } void Or16(int d, int s) { int v = RegPair(d) | RegPair(s); SetRegPair(d, (ushort)v); Flag16(v, true, 0); } void Xor16(int d, int s) { int v = RegPair(d) ^ RegPair(s); SetRegPair(d, (ushort)v); Flag16(v, true, 0); }
    void Shl16(int r) { int v = RegPair(r); SetRegPair(r, (ushort)(v << 1)); Flag16(v << 1, true, v & 0x8000); } void Shr16(int r) { int v = RegPair(r); SetRegPair(r, (ushort)(v >> 1)); Flag16(v >> 1, true, v & 1); } void Rlc16(int r) { int v = RegPair(r); int c = v & 0x8000; v = ((v << 1) | ((flags & C) != 0 ? 1 : 0)) & 0xFFFF; SetRegPair(r, (ushort)v); Flag16(v, true, c); } void Rrc16(int r) { int v = RegPair(r); int c = v & 1; v = (v >> 1) | ((flags & C) != 0 ? 0x8000 : 0); SetRegPair(r, (ushort)v); Flag16(v, true, c); }

    void Unknown() { throw new InvalidOperationException(String.Format("unknown/unsupported opcode {0:X2} near {1:X4} next={2:X2} {3:X2} {4:X2} {5:X2} {6:X2} {7:X2}", op, (ushort)(PC - 1), Peek(PC), Peek((ushort)(PC + 1)), Peek((ushort)(PC + 2)), Peek((ushort)(PC + 3)), Peek((ushort)(PC + 4)), Peek((ushort)(PC + 5)))); }
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
    public int InterruptDepth { get { return interruptStack.Count; } }
    public ushort DmaAddr { get { return dmaAddr; } }
    public ushort DmaCount { get { return dmaCount; } }
    public byte DmaMode { get { return dmaMode; } }
    public bool FloppyMounted { get { return floppyImage != null; } }
    public bool HawkMounted { get { return hawkImage != null; } }
    public byte FfcCommand { get { return ffcCommand; } }
    public byte FfcStatus { get { return ffcStatus; } }
    public byte FfcResult { get { return ffcResult; } }
    public int FfcCommandLength { get { return ffcCommandBuffer == null ? 0 : ffcCommandBuffer.Length; } }
    public byte FloppyCommand { get { return floppyCommand; } }
    public byte FloppyStatus { get { return floppyStatus; } }
    public byte FloppyUnit { get { return floppyUnit; } }
    public byte FloppyTrack { get { return floppyTrack; } }
    public byte FloppySector { get { return floppySector; } }
    public byte FloppyHead { get { return floppyHead; } }
    public byte HawkCommand { get { return hawkCommand; } }
    public byte HawkStatus { get { return hawkStatus; } }
    public byte HawkDriveStatus { get { return hawkDriveStatus; } }
    public byte HawkUnit { get { return hawkUnit; } }
    public ushort HawkSectorAddress { get { return hawkSectorAddress; } }
    public int HawkCylinder { get { return (hawkSectorAddress >> 5) & 0x7FF; } }
    public int HawkHead { get { return (hawkSectorAddress >> 4) & 1; } }
    public int HawkSector { get { return hawkSectorAddress & 0x0F; } }
    public string CvitMode
    {
        get
        {
            if (debugDepositActive) return "DEBUG DEPOSIT";
            if (cedActive) return "CED";
            if (keyTraceActive) return "KEY TRACE";
            return "COMMAND";
        }
    }
    public string CvitPrefixDisplay { get { return $"H{currentCvitDevice}:{currentCvitPrefix}"; } }
    public string CvitActiveFileDisplay { get { return cedActiveDisplay; } }
    public string CommandLineBufferText
    {
        get
        {
            var s = new StringBuilder();
            for (int i = 0; i < 32; i++)
            {
                byte ch = (byte)(mem[(ushort)(CommandLineBuffer + i)] & 0x7F);
                if (ch == 0 || ch == '\r' || ch == '\n') break;
                s.Append(ch >= 32 && ch < 127 ? (char)ch : '.');
            }
            return s.ToString();
        }
    }
    public string LastTerminalKeyDisplay
    {
        get
        {
            if (!haveLastTerminalKey) return "";
            byte ch = (byte)(lastTerminalKey & 0x7F);
            string name = ch switch { 0x08 => "BS", 0x09 => "TAB", 0x0A => "LF", 0x0D => "CR", 0x1B => "ESC", 0x7F => "DEL", _ => ch >= 32 && ch < 127 ? ((char)ch).ToString() : "CTRL" };
            return $"${ch:X2} {name}";
        }
    }
    public void QueueTerminalInput(byte b)
    {
        lastTerminalKey = b;
        haveLastTerminalKey = true;
        if (debugDepositActive) DebugDepositKey(b);
        else if (cedActive) CedKey(b);
        else if (keyTraceActive) KeyTraceKey(b);
        else terminalInput.Enqueue(b);
    }
}

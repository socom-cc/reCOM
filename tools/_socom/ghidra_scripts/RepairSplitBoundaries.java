// soCOM governed repair socom:work:ghidra-repair-split-function-boundaries.
//
// The one reviewed exception to the no-scripts rule (user decision
// 2026-10-30): GhidraMCP 6.0.0 has no endpoint that sets a function body or
// clears a thunk. Only `python tools/socom.py ghidra repair-boundaries` runs
// this file, through the bridge's run_script_inline endpoint; the command
// refuses a file whose SHA-256 differs from the one pinned in
// tools/_socom/repairs.py and passes only that spec's addresses.
//
// Each argument is S:L:E in hex: the .symtab start S, the split piece L, and
// the exclusive .symtab end E. Before any change the script refuses unless,
// for every argument, the function at S is a non-default-named thunk of the
// default-named FUN_ at L, the body of S is exactly [S, L), the body of L is
// exactly [L, E), only S is a thunk of L, every 4-byte address in [S, E) is
// an instruction inside S or L, and L has no tags, call fixup, no-return flag
// or stored symbol other than its own.
//
// It then, inside one nested transaction, clears the thunk at S (first:
// removing L would also delete a thunk of L), removes the function at L, and
// sets the body of S to [S, E). It checks the result before it commits; any
// difference or exception aborts the nested transaction, and Ghidra then
// rolls back the whole script transaction. It clears no flow, writes no
// bytes, disassembles nothing and starts no analysis. Its result is one line:
// SOCOM_REPAIR_BOUNDARIES_RESULT followed by a JSON object.
//@category soCOM

import java.util.ArrayList;
import java.util.List;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.symbol.SourceType;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolTable;

public class RepairSplitBoundaries extends GhidraScript {

	private static final String RESULT = "SOCOM_REPAIR_BOUNDARIES_RESULT ";
	private static final String PROGRAM = "/socom.elf";

	private static final class Split {
		final Address start;
		final Address split;
		final Address last;
		String name = "";

		Split(Address start, Address split, Address last) {
			this.start = start;
			this.split = split;
			this.last = last;
		}
	}

	@Override
	public void run() throws Exception {
		List<String> problems = new ArrayList<>();
		FunctionManager functions = currentProgram.getFunctionManager();
		int before = functions.getFunctionCount();
		String path = currentProgram.getDomainFile().getPathname();
		if (!PROGRAM.equals(path)) {
			problems.add("program is " + path + ", not " + PROGRAM);
		}
		List<Split> splits = parse(getScriptArgs(), problems);
		if (problems.isEmpty()) {
			for (Split split : splits) {
				check(split, problems);
			}
		}
		if (!problems.isEmpty()) {
			report(false, before, -1, splits, problems);
			return;
		}
		int transaction = currentProgram.startTransaction("soCOM repair split function boundaries");
		boolean commit = false;
		int after = -1;
		try {
			for (Split split : splits) {
				rejoin(split);
			}
			after = functions.getFunctionCount();
			if (after != before - splits.size()) {
				problems.add("function count is " + after + ", expected " + (before - splits.size()));
			}
			for (Split split : splits) {
				verify(split, problems);
			}
			commit = problems.isEmpty();
		}
		catch (Exception e) {
			problems.add(e.getClass().getSimpleName() + ": " + e.getMessage());
		}
		finally {
			currentProgram.endTransaction(transaction, commit);
		}
		report(commit, before, commit ? after : -1, splits, problems);
	}

	private List<Split> parse(String[] args, List<String> problems) {
		List<Split> splits = new ArrayList<>();
		if (args == null || args.length == 0) {
			problems.add("no S:L:E arguments");
			return splits;
		}
		long previousEnd = -1;
		for (String arg : args) {
			String[] parts = arg.split(":", -1);
			if (parts.length != 3) {
				problems.add("argument " + arg + " is not S:L:E");
				continue;
			}
			long start = number(parts[0], problems);
			long split = number(parts[1], problems);
			long end = number(parts[2], problems);
			if (start < 0 || split < 0 || end < 0) {
				continue;
			}
			if ((start | split | end) % 4 != 0 || split - start <= 8 || end <= split ||
				start < previousEnd) {
				problems.add("argument " + arg + " is not an ordered aligned S < L < E (L - S > 8)");
				continue;
			}
			previousEnd = end;
			splits.add(new Split(toAddr(start), toAddr(split), toAddr(end - 1)));
		}
		return splits;
	}

	private static long number(String text, List<String> problems) {
		if (!text.startsWith("0x") || text.length() < 3 || text.length() > 10) {
			problems.add(text + " is not a 0x-prefixed 32-bit address");
			return -1;
		}
		try {
			return Long.parseLong(text.substring(2), 16);
		}
		catch (NumberFormatException e) {
			problems.add(text + " is not a 0x-prefixed 32-bit address");
			return -1;
		}
	}

	private void check(Split split, List<String> problems) {
		FunctionManager functions = currentProgram.getFunctionManager();
		Function entry = functions.getFunctionAt(split.start);
		Function piece = functions.getFunctionAt(split.split);
		String at = hex(split.start);
		if (entry == null || piece == null) {
			problems.add(at + ": no function at " + (entry == null ? at : hex(split.split)));
			return;
		}
		split.name = entry.getName();
		Function target = entry.getThunkedFunction(false);
		if (target == null || !target.getEntryPoint().equals(split.split)) {
			problems.add(at + ": not a thunk of " + hex(split.split));
		}
		if (entry.getSymbol().getSource() == SourceType.DEFAULT) {
			problems.add(at + ": has a default name, which a thunk takes from its target");
		}
		if (piece.isThunk() || piece.getSymbol().getSource() != SourceType.DEFAULT) {
			problems.add(hex(split.split) + ": not a default-named non-thunk function");
		}
		Address[] thunks = piece.getFunctionThunkAddresses(false);
		if (thunks == null || thunks.length != 1 || !thunks[0].equals(split.start)) {
			problems.add(hex(split.split) + ": is not the target of exactly one thunk, " + at);
		}
		if (!entry.getBody().hasSameAddresses(new AddressSet(split.start, split.split.previous()))) {
			problems.add(at + ": body is " + entry.getBody() + ", not [" + at + ", " +
				hex(split.split) + ")");
		}
		if (!piece.getBody().hasSameAddresses(new AddressSet(split.split, split.last))) {
			problems.add(hex(split.split) + ": body is " + piece.getBody());
		}
		if (!piece.getTags().isEmpty() || piece.getCallFixup() != null || piece.hasNoReturn()) {
			problems.add(hex(split.split) + ": has tags, a call fixup or the no-return flag");
		}
		Listing listing = currentProgram.getListing();
		for (Address address = split.start; address.compareTo(split.last) <= 0; address =
			address.add(4)) {
			Function owner = functions.getFunctionContaining(address);
			if (listing.getInstructionAt(address) == null || owner == null ||
				!(owner.getEntryPoint().equals(split.start) ||
					owner.getEntryPoint().equals(split.split))) {
				problems.add(hex(address) + ": not an instruction of " + at + " or " +
					hex(split.split));
			}
		}
		SymbolTable symbols = currentProgram.getSymbolTable();
		for (Address address = split.split; address.compareTo(split.last) <= 0; address =
			address.next()) {
			for (Symbol symbol : symbols.getSymbols(address)) {
				if (!symbol.isDynamic() && !symbol.equals(piece.getSymbol())) {
					problems.add(hex(address) + ": has symbol " + symbol.getName(true));
				}
			}
		}
	}

	private void rejoin(Split split) throws Exception {
		FunctionManager functions = currentProgram.getFunctionManager();
		Function entry = functions.getFunctionAt(split.start);
		entry.setThunkedFunction(null);
		if (entry.isThunk()) {
			throw new IllegalStateException(hex(split.start) + " is still a thunk");
		}
		if (!functions.removeFunction(split.split)) {
			throw new IllegalStateException("could not remove the function at " + hex(split.split));
		}
		entry = functions.getFunctionAt(split.start);
		if (entry == null) {
			throw new IllegalStateException("removing " + hex(split.split) + " removed " +
				hex(split.start));
		}
		entry.setBody(new AddressSet(split.start, split.last));
	}

	private void verify(Split split, List<String> problems) {
		FunctionManager functions = currentProgram.getFunctionManager();
		Function entry = functions.getFunctionAt(split.start);
		String at = hex(split.start);
		if (entry == null || entry.isThunk() || !entry.getName().equals(split.name) ||
			!entry.getBody().hasSameAddresses(new AddressSet(split.start, split.last))) {
			problems.add(at + ": not one non-thunk function " + split.name + " over [" + at +
				", " + hex(split.last.next()) + ")");
		}
		if (functions.getFunctionAt(split.split) != null) {
			problems.add(hex(split.split) + ": still has a function");
		}
		for (Address address = split.start; address.compareTo(split.last) <= 0; address =
			address.add(4)) {
			Function owner = functions.getFunctionContaining(address);
			if (owner == null || !owner.getEntryPoint().equals(split.start)) {
				problems.add(hex(address) + ": not inside " + at);
			}
		}
	}

	private void report(boolean ok, int before, int after, List<Split> splits,
			List<String> problems) {
		StringBuilder out = new StringBuilder(RESULT);
		out.append("{\"ok\":").append(ok);
		out.append(",\"changed\":").append(ok);
		out.append(",\"program\":").append(quote(currentProgram.getDomainFile().getPathname()));
		out.append(",\"function_count_before\":").append(before);
		out.append(",\"function_count_after\":").append(after < 0 ? "null" : Integer.toString(after));
		out.append(",\"functions\":[");
		for (int i = 0; i < splits.size(); i++) {
			Split split = splits.get(i);
			out.append(i == 0 ? "" : ",");
			out.append("{\"entry\":").append(quote(hex(split.start)));
			out.append(",\"split\":").append(quote(hex(split.split)));
			out.append(",\"end\":").append(quote(hex(split.last.next())));
			out.append(",\"name\":").append(quote(split.name)).append('}');
		}
		out.append("],\"problems\":[");
		for (int i = 0; i < problems.size(); i++) {
			out.append(i == 0 ? "" : ",").append(quote(problems.get(i)));
		}
		out.append("]}");
		println(out.toString());
	}

	private static String hex(Address address) {
		return "0x" + Long.toHexString(address.getOffset());
	}

	private static String quote(String text) {
		StringBuilder out = new StringBuilder("\"");
		for (char c : text.toCharArray()) {
			if (c == '"' || c == '\\') {
				out.append('\\').append(c);
			}
			else if (c < 0x20 || c > 0x7e) {
				out.append(String.format("\\u%04x", (int) c));
			}
			else {
				out.append(c);
			}
		}
		return out.append('"').toString();
	}
}

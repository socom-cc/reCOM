// soCOM governed export of the prototype's data types to a file archive.
//
// The second reviewed exception to the no-scripts rule (user decision
// 2026-11-25): GhidraMCP 6.0.0 has no endpoint that writes a data type
// archive. Only `python tools/socom.py ghidra type-archive` runs this file,
// through the bridge's run_script_inline endpoint; the command refuses a file
// whose SHA-256 differs from the one pinned in tools/_socom/type_archive.py.
//
// The script only reads the program. Its arguments are the absolute output
// path as hex of its UTF-8 bytes, and `create` or `replace`. Before any file
// is written it refuses unless the program is /socom.elf with language
// r5900:LE:32:default and compiler spec default, the output name ends .gdt in
// an existing directory, the file is absent (or, with `replace`, a plain file
// no Ghidra lock names), and no program type has a .conflict name.
//
// It creates the archive under the final name inside a new staging directory
// next to the output, with the program's language and compiler spec (so its
// data organization is the program's), creates every program category in it,
// and resolves every program type into it in the archive's own transaction
// (DataTypeConflictHandler.DEFAULT_HANDLER: a clash would show as a .conflict
// name, never as a silent replacement). It saves and closes the archive,
// reopens it read-only, and requires the same category paths, the same type
// paths, an equivalent type of the same length at every path, the same count
// per kind, the program's language, compiler spec and data organization, and
// no archive warning. Only then does it move the file onto the output path;
// on any problem it deletes the staging directory, so nothing half-written
// is left.
//
// Around the copy it records the program's database modification count,
// modification number, changed flag, type count and source archives; any
// difference is a failure, and the script then aborts a nested program
// transaction so Ghidra rolls back the script transaction. It associates no
// type with the archive, writes no source-archive record into the program,
// renames nothing and saves nothing. Its result is one line:
// SOCOM_TYPE_ARCHIVE_RESULT followed by a JSON object, which names the archive
// file but never a directory.
//@category soCOM

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Stream;

import ghidra.app.script.GhidraScript;
import ghidra.framework.data.DomainObjectAdapterDB;
import ghidra.program.model.data.Array;
import ghidra.program.model.data.BuiltInDataType;
import ghidra.program.model.data.Category;
import ghidra.program.model.data.CategoryPath;
import ghidra.program.model.data.DataType;
import ghidra.program.model.data.DataTypeConflictHandler;
import ghidra.program.model.data.DataTypeManager;
import ghidra.program.model.data.FileDataTypeManager;
import ghidra.program.model.data.FunctionDefinition;
import ghidra.program.model.data.Pointer;
import ghidra.program.model.data.SourceArchive;
import ghidra.program.model.data.StandAloneDataTypeManager;
import ghidra.program.model.data.Structure;
import ghidra.program.model.data.TypeDef;
import ghidra.program.model.data.Union;
import ghidra.program.model.lang.CompilerSpecID;
import ghidra.program.model.lang.LanguageID;
import ghidra.program.model.lang.ProgramArchitecture;

public class ExportTypeArchive extends GhidraScript {

	private static final String RESULT = "SOCOM_TYPE_ARCHIVE_RESULT ";
	private static final String PROGRAM = "/socom.elf";
	private static final String LANGUAGE = "r5900:LE:32:default";
	private static final String COMPILER = "default";
	private static final String[] KINDS = { "structure", "union", "enum", "typedef",
		"function_definition", "pointer", "array", "builtin", "other" };
	private static final int EXAMPLES = 20;

	private final List<String> problems = new ArrayList<>();
	private final Map<String, Object> result = new LinkedHashMap<>();
	private String outputDirectory;
	private String stagingDirectory;

	@Override
	public void run() throws Exception {
		result.put("ok", false);
		result.put("written", false);
		result.put("program", currentProgram.getDomainFile().getPathname());
		File target = parse(getScriptArgs());
		String mode = result.containsKey("mode") ? (String) result.get("mode") : "";
		checkProgram();
		DataTypeManager programTypes = currentProgram.getDataTypeManager();
		Map<String, Object> before = problems.isEmpty() ? state(programTypes) : null;
		List<DataType> types = new ArrayList<>();
		List<CategoryPath> categories = new ArrayList<>();
		if (problems.isEmpty()) {
			Iterator<DataType> all = programTypes.getAllDataTypes();
			while (all.hasNext()) {
				types.add(all.next());
			}
			collectCategories(programTypes.getRootCategory(), categories);
			result.put("program_counts", counts(types));
			result.put("program_categories", categories.size());
			List<String> conflicts = conflictNames(types);
			result.put("program_conflict_names", conflicts.size());
			if (!conflicts.isEmpty()) {
				problems.add("the program has .conflict types: " + examples(conflicts));
			}
			checkTarget(target, mode);
		}
		if (problems.isEmpty()) {
			export(target, mode, programTypes, types, categories, before);
		}
		if (before != null) {
			Map<String, Object> after = state(programTypes);
			result.put("program_state_before", before);
			result.put("program_state_after", after);
			boolean unchanged = before.equals(after);
			result.put("program_unchanged", unchanged);
			if (!unchanged) {
				problems.add("the program changed while the script ran; the script transaction " +
					"is rolled back");
				int abort = currentProgram.startTransaction("soCOM type archive: discard changes");
				currentProgram.endTransaction(abort, false);
			}
		}
		if (!problems.isEmpty() && Boolean.TRUE.equals(result.get("written"))) {
			problems.add("the archive was already moved onto the output path");
		}
		result.put("ok", problems.isEmpty());
		result.put("problems", problems);
		println(RESULT + json(result));
	}

	private File parse(String[] args) {
		if (args == null || args.length != 2) {
			problems.add("expected two arguments: <hex output path> <create|replace>");
			return null;
		}
		String mode = args[1];
		if (!mode.equals("create") && !mode.equals("replace")) {
			problems.add("mode is " + mode + ", not create or replace");
		}
		result.put("mode", mode);
		String hex = args[0];
		if (hex.isEmpty() || hex.length() % 2 != 0 || !hex.matches("[0-9a-f]+")) {
			problems.add("the output path is not lower-case hex of UTF-8 bytes");
			return null;
		}
		byte[] bytes = new byte[hex.length() / 2];
		for (int i = 0; i < bytes.length; i++) {
			bytes[i] = (byte) Integer.parseInt(hex.substring(2 * i, 2 * i + 2), 16);
		}
		File target = new File(new String(bytes, StandardCharsets.UTF_8));
		result.put("archive", target.getName());
		if (!target.isAbsolute()) {
			problems.add("the output path is not absolute");
			return null;
		}
		File parent = target.getParentFile();
		if (parent == null || !parent.isDirectory()) {
			problems.add("the output directory does not exist");
			return null;
		}
		outputDirectory = parent.getAbsolutePath();
		if (!target.getName().endsWith(FileDataTypeManager.SUFFIX) ||
			target.getName().length() <= FileDataTypeManager.SUFFIX.length()) {
			problems.add(target.getName() + " does not end with " + FileDataTypeManager.SUFFIX);
		}
		return target;
	}

	private void checkProgram() {
		String path = currentProgram.getDomainFile().getPathname();
		if (!PROGRAM.equals(path)) {
			problems.add("program is " + path + ", not " + PROGRAM);
		}
		String language = currentProgram.getLanguageID().getIdAsString();
		String compiler = currentProgram.getCompilerSpec().getCompilerSpecID().getIdAsString();
		if (!LANGUAGE.equals(language) || !COMPILER.equals(compiler)) {
			problems.add("program language is " + language + "/" + compiler + ", not " +
				LANGUAGE + "/" + COMPILER);
		}
		if (!(currentProgram instanceof DomainObjectAdapterDB)) {
			problems.add("the program is not database-backed");
		}
	}

	private void checkTarget(File target, String mode) {
		if (target == null) {
			return;
		}
		if (target.exists()) {
			if (!mode.equals("replace")) {
				problems.add(target.getName() + " exists; pass replace to overwrite it");
			}
			else if (!target.isFile()) {
				problems.add(target.getName() + " exists and is not a file");
			}
		}
		String[] siblings = target.getParentFile().list();
		if (siblings == null) {
			problems.add("the output directory cannot be listed");
			return;
		}
		for (String sibling : siblings) {
			if (sibling.startsWith(target.getName() + ".") && sibling.endsWith("lock")) {
				problems.add(target.getName() + " has a Ghidra lock file (" + sibling +
					"); close the archive first");
			}
		}
	}

	private void export(File target, String mode, DataTypeManager programTypes,
			List<DataType> types, List<CategoryPath> categories, Map<String, Object> before) {
		Path staging = null;
		FileDataTypeManager archive = null;
		try {
			staging = Files.createTempDirectory(target.getParentFile().toPath(),
				".socom-type-archive-");
			stagingDirectory = staging.toFile().getAbsolutePath();
			File staged = new File(staging.toFile(), target.getName());
			archive = FileDataTypeManager.createFileArchive(staged, new LanguageID(LANGUAGE),
				new CompilerSpecID(COMPILER));
			int transaction = archive.startTransaction("soCOM prototype data types");
			boolean commit = false;
			try {
				for (CategoryPath path : categories) {
					archive.createCategory(path);
				}
				archive.addDataTypes(types, DataTypeConflictHandler.DEFAULT_HANDLER, monitor);
				commit = true;
			}
			finally {
				archive.endTransaction(transaction, commit);
			}
			archive.save();
			archive.close();
			archive = null;
			FileDataTypeManager reopened = FileDataTypeManager.openFileArchive(staged, false);
			try {
				verify(reopened, programTypes, types, categories);
			}
			finally {
				reopened.close();
			}
			if (!state(programTypes).equals(before)) {
				problems.add("the program changed during the copy");
			}
			if (problems.isEmpty()) {
				if (mode.equals("replace")) {
					// One rename that replaces the old file (MoveFileEx on Windows).
					Files.move(staged.toPath(), target.toPath(), StandardCopyOption.ATOMIC_MOVE,
						StandardCopyOption.REPLACE_EXISTING);
				}
				else {
					// A same-directory rename that fails if the file appeared meanwhile.
					Files.move(staged.toPath(), target.toPath());
				}
				result.put("written", true);
			}
		}
		catch (Exception e) {
			problems.add(e.getClass().getSimpleName() + ": " + e.getMessage());
		}
		finally {
			if (archive != null) {
				archive.close();
			}
			if (staging != null) {
				removeStaging(staging);
			}
		}
	}

	private void verify(FileDataTypeManager archive, DataTypeManager programTypes,
			List<DataType> types, List<CategoryPath> categories) {
		StandAloneDataTypeManager.ArchiveWarning warning = archive.getWarning();
		result.put("archive_warning", warning.name());
		if (warning != StandAloneDataTypeManager.ArchiveWarning.NONE) {
			problems.add("the reopened archive warns " + warning.name());
		}
		ProgramArchitecture architecture = archive.getProgramArchitecture();
		Map<String, Object> arch = new LinkedHashMap<>();
		if (architecture == null) {
			problems.add("the reopened archive has no program architecture");
		}
		else {
			arch.put("language", architecture.getLanguage().getLanguageID().getIdAsString());
			arch.put("compiler_spec",
				architecture.getCompilerSpec().getCompilerSpecID().getIdAsString());
			if (!LANGUAGE.equals(arch.get("language")) || !COMPILER.equals(arch.get("compiler_spec"))) {
				problems.add("the reopened archive architecture is " + arch);
			}
		}
		result.put("archive_architecture", arch);
		boolean organization =
			archive.getDataOrganization().equals(programTypes.getDataOrganization());
		result.put("data_organization_equal", organization);
		result.put("pointer_size", archive.getDataOrganization().getPointerSize());
		if (!organization) {
			problems.add("the archive data organization differs from the program's");
		}
		result.put("universal_id", Long.toString(archive.getUniversalID().getValue()));

		List<CategoryPath> archiveCategories = new ArrayList<>();
		collectCategories(archive.getRootCategory(), archiveCategories);
		result.put("archive_categories", archiveCategories.size());
		Set<String> wanted = new TreeSet<>();
		for (CategoryPath path : categories) {
			wanted.add(path.getPath());
		}
		Set<String> found = new TreeSet<>();
		for (CategoryPath path : archiveCategories) {
			found.add(path.getPath());
		}
		if (!wanted.equals(found)) {
			problems.add("the archive categories differ from the program's");
		}

		List<DataType> archived = new ArrayList<>();
		Iterator<DataType> all = archive.getAllDataTypes();
		while (all.hasNext()) {
			archived.add(all.next());
		}
		Map<String, Integer> archiveCounts = counts(archived);
		result.put("archive_counts", archiveCounts);
		if (!archiveCounts.equals(result.get("program_counts"))) {
			problems.add("the archive type counts differ from the program's");
		}
		List<String> conflicts = conflictNames(archived);
		result.put("conflict_names", conflicts.size());
		if (!conflicts.isEmpty()) {
			problems.add("the archive has .conflict types: " + examples(conflicts));
		}
		Set<String> programPaths = new TreeSet<>();
		for (DataType type : types) {
			programPaths.add(type.getPathName());
		}
		Set<String> archivePaths = new TreeSet<>();
		for (DataType type : archived) {
			archivePaths.add(type.getPathName());
		}
		List<String> missing = new ArrayList<>();
		for (String path : programPaths) {
			if (!archivePaths.contains(path)) {
				missing.add(path);
			}
		}
		List<String> extra = new ArrayList<>();
		for (String path : archivePaths) {
			if (!programPaths.contains(path)) {
				extra.add(path);
			}
		}
		result.put("missing", missing.size());
		result.put("extra", extra.size());
		if (!missing.isEmpty() || !extra.isEmpty()) {
			problems.add("type paths differ; missing " + examples(missing) + ", extra " +
				examples(extra));
		}
		List<String> different = new ArrayList<>();
		for (DataType type : types) {
			DataType copy = archive.getDataType(type.getCategoryPath(), type.getName());
			if (copy != null && (copy.getLength() != type.getLength() || !copy.isEquivalent(type))) {
				different.add(type.getPathName());
			}
		}
		result.put("not_equivalent", different.size());
		if (!different.isEmpty()) {
			problems.add("archive types differ from the program's: " + examples(different));
		}
	}

	private Map<String, Object> state(DataTypeManager programTypes) {
		Map<String, Object> state = new LinkedHashMap<>();
		if (currentProgram instanceof DomainObjectAdapterDB database) {
			state.put("database_mod_count", database.getDBHandle().getModCount());
		}
		state.put("modification_number", currentProgram.getModificationNumber());
		state.put("changed", currentProgram.isChanged());
		state.put("type_count", programTypes.getDataTypeCount(true));
		List<String> archives = new ArrayList<>();
		for (SourceArchive archive : programTypes.getSourceArchives()) {
			archives.add(archive.getArchiveType().name() + ":" + archive.getName() + ":" +
				archive.getSourceArchiveID().getValue());
		}
		Collections.sort(archives);
		state.put("source_archives", archives);
		return state;
	}

	private static void collectCategories(Category category, List<CategoryPath> out) {
		Category[] children = category.getCategories();
		java.util.Arrays.sort(children, Comparator.comparing(child -> child.getCategoryPath().getPath()));
		for (Category child : children) {
			out.add(child.getCategoryPath());
			collectCategories(child, out);
		}
	}

	private static String kind(DataType type) {
		if (type instanceof Pointer) {
			return "pointer";
		}
		if (type instanceof Array) {
			return "array";
		}
		if (type instanceof Structure) {
			return "structure";
		}
		if (type instanceof Union) {
			return "union";
		}
		if (type instanceof ghidra.program.model.data.Enum) {
			return "enum";
		}
		if (type instanceof TypeDef) {
			return "typedef";
		}
		if (type instanceof FunctionDefinition) {
			return "function_definition";
		}
		if (type instanceof BuiltInDataType) {
			return "builtin";
		}
		return "other";
	}

	private static Map<String, Integer> counts(List<DataType> types) {
		Map<String, Integer> counts = new LinkedHashMap<>();
		counts.put("total", types.size());
		for (String kind : KINDS) {
			counts.put(kind, 0);
		}
		for (DataType type : types) {
			counts.merge(kind(type), 1, Integer::sum);
		}
		return counts;
	}

	private static List<String> conflictNames(List<DataType> types) {
		List<String> names = new ArrayList<>();
		for (DataType type : types) {
			if (type.getName().contains(DataType.CONFLICT_SUFFIX)) {
				names.add(type.getPathName());
			}
		}
		return names;
	}

	private static String examples(List<String> values) {
		List<String> head = values.subList(0, Math.min(EXAMPLES, values.size()));
		return head + (values.size() > EXAMPLES ? " and " + (values.size() - EXAMPLES) + " more" : "");
	}

	private void removeStaging(Path staging) {
		try (Stream<Path> walk = Files.walk(staging)) {
			List<Path> paths = new ArrayList<>(walk.toList());
			Collections.reverse(paths);
			for (Path path : paths) {
				Files.deleteIfExists(path);
			}
		}
		catch (IOException e) {
			problems.add("the staging directory was not removed: " + e.getClass().getSimpleName());
		}
	}

	private String clean(String text) {
		String out = text == null ? "" : text;
		String[][] directories =
			{ { stagingDirectory, "<staging-dir>" }, { outputDirectory, "<output-dir>" } };
		for (String[] directory : directories) {
			if (directory[0] != null) {
				out = out.replace(directory[0], directory[1])
						.replace(directory[0].replace('\\', '/'), directory[1]);
			}
		}
		return out;
	}

	private String json(Object value) {
		if (value == null) {
			return "null";
		}
		if (value instanceof Boolean || value instanceof Integer || value instanceof Long) {
			return value.toString();
		}
		if (value instanceof Map<?, ?> map) {
			StringBuilder out = new StringBuilder("{");
			boolean first = true;
			for (Map.Entry<?, ?> entry : map.entrySet()) {
				out.append(first ? "" : ",").append(quote(entry.getKey().toString())).append(':');
				out.append(json(entry.getValue()));
				first = false;
			}
			return out.append('}').toString();
		}
		if (value instanceof List<?> list) {
			StringBuilder out = new StringBuilder("[");
			for (int i = 0; i < list.size(); i++) {
				out.append(i == 0 ? "" : ",").append(json(list.get(i)));
			}
			return out.append(']').toString();
		}
		return quote(clean(value.toString()));
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

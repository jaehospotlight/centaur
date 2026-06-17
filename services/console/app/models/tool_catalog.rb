require "pathname"
require "toml-rb"

# Read-only catalog of Centaur tool manifests visible to the console process.
# Mirrors api-rs discovery: each TOOL_DIRS root may contain tool directories
# directly, or one category level that contains tool directories.
class ToolCatalog
  Tool = Data.define(:name, :path, :source_root, :module_path, :secrets, :optional_secrets)
  Secret = Data.define(:name, :type, :mode, :hosts, :target, :optional)

  def initialize(tool_dirs: ENV.fetch("TOOL_DIRS", ""))
    @tool_dirs = tool_dirs.to_s.split(":").map(&:strip).reject(&:empty?).map { |dir| Pathname.new(dir) }
  end

  def tools
    by_name = {}
    tool_dirs.each do |root|
      candidate_tool_dirs(root).each do |tool_dir|
        tool = load_tool(root, tool_dir)
        by_name[tool.name] = tool if tool
      end
    end
    by_name.values.sort_by(&:name)
  end

  def tool_dirs
    @tool_dirs
  end

  private

  def candidate_tool_dirs(root)
    return [] unless root.directory?

    root.children.select(&:directory?).reject { |path| hidden?(path) }.sort.flat_map do |child|
      if child.join("pyproject.toml").file?
        [ child ]
      else
        child.children.select(&:directory?)
          .reject { |path| hidden?(path) }
          .select { |path| path.join("pyproject.toml").file? }
          .sort
      end
    end
  end

  def load_tool(source_root, tool_dir)
    pyproject = TomlRB.load_file(tool_dir.join("pyproject.toml").to_s)
    centaur = pyproject.dig("tool", "centaur") || {}
    return nil if centaur["type"] == "persona"

    secrets = parse_secrets(centaur["secrets"], optional: false)
    optional_secrets = parse_secrets(centaur["optional_secrets"], optional: true)
    Tool.new(
      name: tool_dir.basename.to_s,
      path: tool_dir.to_s,
      source_root: source_root.to_s,
      module_path: centaur["module"].presence,
      secrets: secrets,
      optional_secrets: optional_secrets
    )
  rescue TomlRB::ParseError, Errno::ENOENT => e
    Rails.logger.warn("tool catalog skipped #{tool_dir}: #{e.class}: #{e.message}")
    nil
  end

  def parse_secrets(entries, optional:)
    Array(entries).filter_map do |entry|
      case entry
      when String
        Secret.new(
          name: entry,
          type: "http",
          mode: "replace",
          hosts: [],
          target: "placeholder",
          optional: optional
        )
      when Hash
        Secret.new(
          name: entry["name"].presence || "unnamed",
          type: entry["type"].presence || "http",
          mode: entry["mode"].presence || "replace",
          hosts: Array(entry["hosts"]),
          target: secret_target(entry),
          optional: optional
        )
      end
    end
  end

  def secret_target(entry)
    return entry["inject_header"] if entry["inject_header"].present?
    return "?#{entry["inject_query_param"]}" if entry["inject_query_param"].present?

    headers = Array(entry["match_headers"])
    return headers.join(", ") if headers.any?

    entry["replacer"].presence || entry["secret_ref"].presence || "placeholder"
  end

  def hidden?(path)
    name = path.basename.to_s
    name.start_with?(".", "_")
  end
end

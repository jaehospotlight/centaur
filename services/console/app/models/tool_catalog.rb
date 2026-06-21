require "toml-rb"

# Reads Centaur tool manifests directly from checked-out tool directories. The
# catalog is intentionally filesystem-backed, not persisted: repo-cache already
# owns freshness and overlay ordering.
class ToolCatalog
  DEFAULT_MATCH_HEADERS = [
    "Authorization",
    "Proxy-Authorization",
    "Api-Key",
    "Anthropic-Api-Key",
    "Auth-Token",
    "Jwt",
    "Cookie",
    "Apikey"
  ].freeze

  Entry = Data.define(
    :key,
    :name,
    :category,
    :description,
    :hosts,
    :manifest_path,
    :source_root,
    :secrets,
    :errors
  ) do
    def secret_count = secrets.size
    def required_secret_count = secrets.count(&:required?)
    def optional_secret_count = secrets.count { |secret| !secret.required? }
  end

  SecretRequirement = Data.define(
    :kind,
    :type,
    :name,
    :secret_ref,
    :required,
    :hosts,
    :mode,
    :inject_header,
    :inject_query_param,
    :inject_formatter,
    :match_headers,
    :match_path,
    :match_query,
    :grant,
    :token_endpoint,
    :scopes,
    :fields,
    :token_endpoint_headers,
    :audience,
    :database,
    :role,
    :settings,
    :access_key_id,
    :secret_access_key,
    :session_token,
    :allowed_regions,
    :allowed_services,
    :labels
  ) do
    def required? = required

    def source_refs
      case kind
      when "aws_auth"
        [ access_key_id, secret_access_key, session_token ].compact
      when "oauth_token"
        fields.values.map { |value| value["secret_ref"] }.compact
      else
        [ secret_ref ].compact
      end
    end
  end

  class << self
    def entries
      new.entries
    end

    def find!(key)
      entries.find { |entry| entry.key == key } or raise ActiveRecord::RecordNotFound, "tool not found"
    end

    def configured_roots
      raw = ENV["CENTAUR_TOOL_CATALOG_DIRS"].presence || ENV["TOOL_DIRS"].presence
      roots = raw.to_s.split(File::PATH_SEPARATOR).map(&:strip).reject(&:blank?)
      roots = [ Rails.root.join("../../tools").expand_path.to_s ] if roots.empty?
      roots
    end

    def slugify(value)
      value.to_s.downcase.gsub(/[^a-z0-9]+/, "-").gsub(/\A-|-+\z/, "")
    end
  end

  def initialize(roots: self.class.configured_roots)
    @roots = roots
  end

  def entries
    by_name = {}
    roots.each do |root|
      next unless Dir.exist?(root)
      Dir.glob(File.join(root, "**", "pyproject.toml")).sort.each do |manifest_path|
        entry = entry_from_manifest(root, manifest_path)
        next unless entry
        by_name[entry.name] = entry
      end
    end
    by_name.values.sort_by { |entry| [ entry.category.to_s, entry.name ] }
  end

  private

  attr_reader :roots

  def entry_from_manifest(root, manifest_path)
    data = TomlRB.load_file(manifest_path)
    centaur = data.dig("tool", "centaur")
    return unless centaur.is_a?(Hash)

    tool_dir = File.dirname(manifest_path)
    name = File.basename(tool_dir)
    rel = Pathname.new(tool_dir).relative_path_from(Pathname.new(root)).to_s
    category = rel == "." ? nil : rel.split(File::SEPARATOR).first
    labels = tool_labels(name, root)
    hosts = string_array(centaur["hosts"])
    secrets, errors = parse_secrets(centaur, hosts, labels)

    Entry.new(
      key: self.class.slugify(name),
      name: name,
      category: category,
      description: data.dig("project", "description").to_s.presence,
      hosts: hosts,
      manifest_path: manifest_path,
      source_root: root,
      secrets: secrets,
      errors: errors
    )
  rescue TomlRB::ParseError, Errno::ENOENT => e
    name = File.basename(File.dirname(manifest_path))
    Entry.new(
      key: self.class.slugify(name),
      name: name,
      category: nil,
      description: nil,
      hosts: [],
      manifest_path: manifest_path,
      source_root: root,
      secrets: [],
      errors: [ e.message ]
    )
  end

  def parse_secrets(centaur, default_hosts, labels)
    secrets = []
    errors = []
    [
      [ centaur["secrets"], true ],
      [ centaur["optional_secrets"], false ]
    ].each do |raw_entries, required|
      Array(raw_entries).each do |raw|
        secrets << parse_secret(raw, default_hosts, labels, required)
      rescue ArgumentError => e
        errors << e.message
      end
    end
    [ secrets, errors ]
  end

  def parse_secret(raw, default_hosts, labels, required)
    if raw.is_a?(String)
      return http_secret(
        { "name" => raw, "match_headers" => DEFAULT_MATCH_HEADERS },
        default_hosts,
        labels,
        required
      )
    end
    raise ArgumentError, "secret entry must be a string or table" unless raw.is_a?(Hash)

    case raw["type"].presence || "http"
    when "http", "header"
      http_secret(raw, default_hosts, labels, required)
    when "gcp_auth"
      basic_secret("gcp_auth", raw, default_hosts, labels, required)
    when "pg_dsn"
      basic_secret("pg_dsn", raw, default_hosts, labels, required)
    when "aws_auth"
      aws_secret(raw, labels, required)
    when "oauth_token"
      oauth_secret(raw, labels, required)
    when "hmac", "hmac_sign"
      basic_secret("hmac", raw, default_hosts, labels, required)
    else
      raise ArgumentError, "unknown secret type #{raw["type"].inspect}"
    end
  end

  def http_secret(raw, default_hosts, labels, required)
    name = required_string(raw, "name")
    mode = raw["mode"].presence || "replace"
    hosts = string_array(raw["hosts"]).presence || default_hosts
    SecretRequirement.new(
      **base_attrs("static", "http", raw, labels, required).merge(
        hosts: hosts,
        mode: mode,
        inject_header: raw["inject_header"].to_s.presence,
        inject_query_param: raw["inject_query_param"].to_s.presence,
        inject_formatter: raw["inject_formatter"].to_s.presence,
        match_headers: string_array(raw["match_headers"]),
        match_path: raw["match_path"] == true,
        match_query: raw["match_query"] == true,
        secret_ref: raw["secret_ref"].to_s.presence || name,
        grant: nil,
        token_endpoint: nil,
        scopes: [],
        fields: {},
        token_endpoint_headers: {},
        audience: nil,
        database: nil,
        role: nil,
        settings: [],
        access_key_id: nil,
        secret_access_key: nil,
        session_token: nil,
        allowed_regions: [],
        allowed_services: []
      )
    )
  end

  def basic_secret(kind, raw, default_hosts, labels, required)
    name = required_string(raw, "name")
    SecretRequirement.new(
      **base_attrs(kind, raw["type"].presence || kind, raw, labels, required).merge(
        secret_ref: raw["secret_ref"].to_s.presence || name,
        hosts: string_array(raw["hosts"]).presence || default_hosts,
        mode: nil,
        inject_header: nil,
        inject_query_param: nil,
        inject_formatter: nil,
        match_headers: [],
        match_path: false,
        match_query: false,
        grant: nil,
        token_endpoint: nil,
        scopes: string_array(raw["scopes"]),
        fields: {},
        token_endpoint_headers: {},
        audience: nil,
        database: raw["database"].to_s.presence,
        role: raw["role"].to_s.presence,
        settings: Array(raw["settings"]),
        access_key_id: nil,
        secret_access_key: nil,
        session_token: nil,
        allowed_regions: [],
        allowed_services: []
      )
    )
  end

  def aws_secret(raw, labels, required)
    name = required_string(raw, "name")
    SecretRequirement.new(
      **base_attrs("aws_auth", "aws_auth", raw, labels, required).merge(
        secret_ref: name,
        hosts: string_array(raw["hosts"]),
        mode: nil,
        inject_header: nil,
        inject_query_param: nil,
        inject_formatter: nil,
        match_headers: [],
        match_path: false,
        match_query: false,
        grant: nil,
        token_endpoint: nil,
        scopes: [],
        fields: {},
        token_endpoint_headers: {},
        audience: nil,
        database: nil,
        role: nil,
        settings: [],
        access_key_id: raw["access_key_id"].to_s.presence,
        secret_access_key: raw["secret_access_key"].to_s.presence,
        session_token: raw["session_token"].to_s.presence,
        allowed_regions: string_array(raw["allowed_regions"]),
        allowed_services: string_array(raw["allowed_services"])
      )
    )
  end

  def oauth_secret(raw, labels, required)
    name = required_string(raw, "name")
    SecretRequirement.new(
      **base_attrs("oauth_token", "oauth_token", raw, labels, required).merge(
        secret_ref: name,
        hosts: string_array(raw["hosts"]),
        mode: nil,
        inject_header: nil,
        inject_query_param: nil,
        inject_formatter: nil,
        match_headers: [],
        match_path: false,
        match_query: false,
        grant: raw["grant"].to_s.presence,
        token_endpoint: raw["token_endpoint"].to_s.presence,
        scopes: string_array(raw["scopes"]),
        fields: source_map(raw["fields"]),
        token_endpoint_headers: source_map(raw["token_endpoint_headers"]),
        audience: raw["audience"].to_s.presence,
        database: nil,
        role: nil,
        settings: [],
        access_key_id: nil,
        secret_access_key: nil,
        session_token: nil,
        allowed_regions: [],
        allowed_services: []
      )
    )
  end

  def base_attrs(kind, type, raw, labels, required)
    {
      kind: kind,
      type: type,
      name: required_string(raw, "name"),
      required: required,
      labels: labels
    }
  end

  def tool_labels(name, root)
    {
      "centaur-tool" => name,
      "centaur-tool-overlay" => File.basename(root.to_s)
    }
  end

  def source_map(raw)
    return {} unless raw.is_a?(Hash)
    raw.transform_values do |value|
      if value.is_a?(String)
        { "secret_ref" => value }
      elsif value.is_a?(Hash)
        value.slice("secret_ref", "json_key")
      else
        {}
      end
    end
  end

  def required_string(raw, key)
    value = raw[key].to_s
    raise ArgumentError, "secret entry is missing #{key.inspect}" if value.blank?
    value
  end

  def string_array(value)
    Array(value).filter_map { |item| item.to_s.presence }
  end
end

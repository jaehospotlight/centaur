module Console
  # Read-only operator catalog of tool manifests from the repo cache. This is a
  # discovery surface only: creating a secret still goes through the existing
  # per-type secret forms.
  class ToolsController < ApplicationController
    include SecretKinds

    layout "console"

    def index
      @tools = ToolCatalog.entries
    end

    def show
      @tool = ToolCatalog.find!(params[:id])
      @matches_by_secret = @tool.secrets.index_with { |secret| matching_secrets(@tool, secret) }
    end

    helper_method :tool_secret_creation_path, :tool_secret_expected_foreign_id

    private

    def matching_secrets(tool, requirement)
      cfg = SECRET_KINDS[requirement.kind]
      return [] unless cfg

      cfg[:model]
        .includes(cfg[:includes])
        .order(:namespace, :id)
        .select { |secret| secret_matches_requirement?(tool, requirement, secret) }
    end

    def secret_matches_requirement?(tool, requirement, secret)
      return true if secret.foreign_id == tool_secret_expected_foreign_id(tool, requirement)
      return true if secret.try(:name) == requirement.name
      return true if secret.labels.is_a?(Hash) && secret.labels["centaur-tool"] == tool.name

      source_refs = secret_source_refs(secret)
      requirement.source_refs.any? do |ref|
        source_refs.include?(ref) ||
          source_refs.include?("op://ai-agents/#{ref}/credential")
      end
    end

    def secret_source_refs(secret)
      sources =
        case secret
        when StaticSecret then [ secret.source ]
        when PgDsnSecret then [ secret.dsn_source ]
        when GcpAuthSecret then [ secret.keyfile_source ]
        when AwsAuthSecret, OauthTokenSecret, HmacSecret then secret.sources
        else []
        end
      sources.compact.filter_map do |source|
        key = SOURCE_REF_KEYS[source.source_type]
        if key && source.config.is_a?(Hash)
          source.config[key].presence
        elsif source.source_type == "control_plane"
          "inline"
        end
      end
    end

    def tool_secret_expected_foreign_id(tool, requirement)
      parts = [ "tool", tool.name, requirement.source_refs.first.presence || requirement.name ]
      parts.map { |part| ToolCatalog.slugify(part) }.reject(&:blank?).join("-")
    end

    def tool_secret_creation_path(tool, requirement)
      return unless secret_form_kinds.key?(requirement.kind)

      params = prefill_params(tool, requirement)
      case requirement.kind
      when "static" then new_console_static_secret_path(params)
      when "gcp_auth" then new_console_gcp_auth_secret_path(params)
      when "pg_dsn" then new_console_pg_dsn_secret_path(params)
      end
    end

    def prefill_params(tool, requirement)
      base = {
        prefill: "1",
        secret: {
          namespace: "default",
          foreign_id: tool_secret_expected_foreign_id(tool, requirement),
          name: requirement.name,
          description: "#{tool.name} tool credential"
        },
        source: {
          source_type: "env",
          reference: requirement.source_refs.first || requirement.name
        },
        labels: label_rows(requirement.labels)
      }
      extra = kind_prefill_params(requirement)
      base[:secret].merge!(extra.delete(:secret) || {})
      base.merge(extra)
    end

    def kind_prefill_params(requirement)
      case requirement.kind
      when "static"
        {
          static: static_prefill(requirement),
          rules: host_rule_rows(requirement.hosts)
        }
      when "gcp_auth"
        {
          gcp: {
            credential_mode: "keyfile",
            scopes: Array(requirement.scopes).join("\n")
          },
          rules: host_rule_rows(requirement.hosts)
        }
      when "pg_dsn"
        {
          secret: {
            namespace: "default",
            name: requirement.name,
            description: "DSN for the #{requirement.name} tool database",
            database: requirement.database,
            role: requirement.role
          },
          settings: setting_rows(requirement.settings)
        }
      else
        {}
      end
    end

    def static_prefill(requirement)
      if requirement.mode == "inject"
        {
          mode: "inject",
          header: requirement.inject_header,
          query_param: requirement.inject_query_param,
          formatter: requirement.inject_formatter
        }
      else
        {
          mode: "replace",
          proxy_value: requirement.name,
          match_headers: Array(requirement.match_headers).join(", "),
          match_path: requirement.match_path ? "1" : nil,
          match_query: requirement.match_query ? "1" : nil
        }
      end
    end

    def host_rule_rows(hosts)
      Array(hosts).each_with_index.to_h do |host, index|
        [ index.to_s, { host: host, http_methods: "", paths: "" } ]
      end
    end

    def setting_rows(settings)
      Array(settings).each_with_index.to_h do |setting, index|
        next [ index.to_s, { name: "", kind: "literal", value: "" } ] unless setting.is_a?(Hash)

        value_from = setting["value_from"]
        if value_from.is_a?(Hash)
          kind, value = value_from.slice("principal_label", "principal_field").first
          [ index.to_s, { name: setting["name"], kind: kind, value: value } ]
        else
          [ index.to_s, { name: setting["name"], kind: "literal", value: setting["value"] } ]
        end
      end
    end

    def label_rows(labels)
      labels.each_with_index.to_h do |(key, value), index|
        [ index.to_s, { key: key, value: value } ]
      end
    end
  end
end

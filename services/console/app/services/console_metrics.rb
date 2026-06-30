class ConsoleMetrics
  METRIC_NAME = "centaur_service_image_info"

  def self.render
    labels = {
      service: "console",
      image: image,
      image_repository: env_value("CENTAUR_IMAGE_REPOSITORY"),
      image_tag: image_tag,
      version: image_tag
    }

    [
      "# HELP #{METRIC_NAME} Static container image metadata for a Centaur service.",
      "# TYPE #{METRIC_NAME} gauge",
      "#{METRIC_NAME}{#{format_labels(labels)}} 1",
      ""
    ].join("\n")
  end

  def self.image
    env_value("CENTAUR_IMAGE", default: "#{env_value("CENTAUR_IMAGE_REPOSITORY")}:#{image_tag}")
  end

  def self.image_tag
    env_value("CENTAUR_IMAGE_TAG", default: env_value("CENTAUR_IMAGE_VERSION"))
  end

  def self.env_value(name, default: "unknown")
    value = ENV[name].to_s.strip
    value.empty? ? default : value
  end

  def self.format_labels(labels)
    labels.map { |key, value| "#{key}=\"#{escape_label_value(value)}\"" }.join(",")
  end

  def self.escape_label_value(value)
    value.to_s.gsub(/[\\\n"]/) do |character|
      case character
      when "\\"
        "\\\\"
      when "\n"
        "\\n"
      else
        "\\\""
      end
    end
  end
end

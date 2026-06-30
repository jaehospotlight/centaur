class MetricsController < ActionController::API
  def show
    render plain: ConsoleMetrics.render,
           content_type: "text/plain; version=0.0.4; charset=utf-8"
  end
end

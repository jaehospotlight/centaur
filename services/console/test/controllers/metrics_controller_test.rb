require "test_helper"

class MetricsControllerTest < ActionDispatch::IntegrationTest
  test "serves image info metrics without login" do
    get "/metrics"

    assert_response :ok
    assert_includes @response.media_type, "text/plain"
    assert_includes @response.body, "# HELP centaur_service_image_info"
    assert_includes @response.body, "# TYPE centaur_service_image_info gauge"
    assert_includes @response.body, 'centaur_service_image_info{service="console"'
    assert_includes @response.body, 'image_repository="'
    assert_includes @response.body, 'image_tag="'
    assert_includes @response.body, 'version="'
  end
end

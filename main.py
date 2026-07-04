from release_tool.api_app import app, main
from release_tool.mail_test_api import register_mail_test_routes

register_mail_test_routes(app)

if __name__ == "__main__":
    main()

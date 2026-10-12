import requests


class TwitterPublisher:
    """
    Publicador de X desacoplado del resto de la aplicación.

    Actualmente utiliza Buffer como proveedor de publicación.
    """

    BUFFER_URL = "https://api.buffer.com"

    def __init__(self, api_key, channel_id):
        if not api_key:
            raise RuntimeError("Falta BUFFER_API_KEY")

        if not channel_id:
            raise RuntimeError("Falta BUFFER_CHANNEL_ID")

        self.api_key = api_key
        self.channel_id = channel_id

    def publish(
        self,
        text,
        media_type=None,
        media_url=None
    ):
        mutation = """
        mutation CreatePost($input: CreatePostInput!) {
          createPost(input: $input) {
            ... on PostActionSuccess {
              post {
                id
                text
                assets {
                  id
                  mimeType
                }
              }
            }

            ... on MutationError {
              message
            }
          }
        }
        """

        input_data = {
            "text": text,
            "channelId": self.channel_id,
            "mode": "shareNow",
            "schedulingType": "automatic"
        }

        if media_url:
            if media_type == "image":
                input_data["assets"] = [
                    {
                        "image": {
                            "url": media_url
                        }
                    }
                ]

            elif media_type == "video":
                input_data["assets"] = [
                    {
                        "video": {
                            "url": media_url
                        }
                    }
                ]

            else:
                raise RuntimeError(
                    f"Tipo de media no soportado: "
                    f"{media_type}"
                )

        response = requests.post(
            self.BUFFER_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "query": mutation,
                "variables": {
                    "input": input_data
                }
            },
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        if data.get("errors"):
            raise RuntimeError(
                f"Buffer GraphQL error: {data['errors']}"
            )

        create_post = (
            data
            .get("data", {})
            .get("createPost")
        )

        if not create_post:
            raise RuntimeError(
                f"Buffer no devolvió createPost: {data}"
            )

        post = create_post.get("post")

        if post:
            return post

        message = create_post.get("message")

        if message:
            raise RuntimeError(
                f"Buffer rechazó el post: {message}"
            )

        raise RuntimeError(
            f"Respuesta inesperada de Buffer: {data}"
        )

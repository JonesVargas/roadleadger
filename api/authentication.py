from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from licenses.models import ApiToken


class HashedTokenAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "").split()
        if not header:
            return None
        if len(header) != 2 or header[0] != self.keyword:
            raise AuthenticationFailed("Cabeçalho de autenticação inválido.")
        token = ApiToken.authenticate(header[1])
        if not token:
            raise AuthenticationFailed("Token inválido ou revogado.")
        return token.user, token

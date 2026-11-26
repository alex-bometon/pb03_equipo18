"""Pruebas del contexto de las peticiones HTTP."""

from uuid import UUID

from fastapi import Request

from api.request_context import REQUEST_ID_HEADER, get_request_id


def crear_peticion(
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    """Construye una petición HTTP aislada."""
    return Request({
        "type": "http",
        "headers": headers or [],
    })


def test_request_id_es_uuid_valido() -> None:
    """Comprueba la generación de un UUID válido."""
    request = crear_peticion()

    request_id = get_request_id(request)

    assert str(UUID(request_id)) == request_id
    assert UUID(request_id).version == 4


def test_request_id_se_almacena_en_state() -> None:
    """Comprueba que el identificador permanece en el contexto."""
    request = crear_peticion()

    request_id = get_request_id(request)

    assert request.state.request_id == request_id


def test_request_id_se_reutiliza() -> None:
    """Conserva el identificador dentro de una misma petición."""
    request = crear_peticion()

    first = get_request_id(request)
    second = get_request_id(request)

    assert first == second


def test_request_id_aislado_entre_peticiones() -> None:
    """Comprueba el aislamiento de los contextos."""
    first = crear_peticion()
    second = crear_peticion()

    assert get_request_id(first) != get_request_id(second)


def test_request_id_ignora_identificador_del_cliente() -> None:
    """Impide que el cliente determine el identificador."""
    provided = "550e8400-e29b-41d4-a716-446655440000"

    request = crear_peticion([
        (
            REQUEST_ID_HEADER.lower().encode("ascii"),
            provided.encode("ascii"),
        ),
    ])

    assert get_request_id(request) != provided
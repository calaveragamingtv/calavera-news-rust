)

        queue = build_content_queue(
            article,
            analysis
        )

        save_json(
            QUEUE_FILE,
            queue
        )

        print()
        print(
            "Cola de contenido creada."
        )

        print(
            "Secciones seleccionadas: "
            f"{len(queue['items'])}"
        )

        # ----------------------------------------------------
        # DIA 1
        # SOLO ANUNCIO GENERAL
        # ----------------------------------------------------

        general_complete = (
            process_general_announcement(
                queue
            )
        )

        if general_complete:
            print()
            print(
                "Anuncio general completado."
            )

        print()
        print(
            "La primera sección queda "
            "para la próxima ejecución."
        )

        return

    # ========================================================
    # ARTICULO YA PROCESADO
    # ========================================================

    print()
    print(
        "Patch ya procesado."
    )

    if not queue:
        print(
            "No existe una cola válida."
        )

        return

    # ========================================================
    # COMPLETAR ANUNCIO GENERAL
    # ========================================================

    publication = queue.get(
        "general_publication",
        {}
    )

    general_complete = (
        publication.get(
            "x_posted",
            False
        )
        and publication.get(
            "discord_posted",
            False
        )
    )

    if not general_complete:
        print()
        print(
            "El anuncio general todavía "
            "no está completo."
        )

        completed_now = (
            process_general_announcement(
                queue
            )
        )

        if completed_now:
            print()
            print(
                "Anuncio general completado."
            )

            print(
                "La primera sección queda "
                "para la próxima ejecución."
            )

        return

    # ========================================================
    # CONTENIDO DIARIO
    # ========================================================

    publish_next_content(
        queue
    )


if __name__ == "__main__":
    main()

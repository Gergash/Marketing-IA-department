package main

import (
	"log"
	"net/http"

	"social-publisher-go/internal/publisher"
)

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", publisher.HealthHandler)
	mux.HandleFunc("/publish", publisher.PublishHandler)

	addr := ":8088"
	log.Printf("social-publisher-go escuchando en %s", addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}

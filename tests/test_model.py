from core.llm import hide_reasoning


def main():
    assert hide_reasoning("<think>private reasoning</think>Final answer") == "Final answer"
    assert hide_reasoning("Useful answer") == "Useful answer"
    print("model reasoning filter tests passed")


if __name__ == "__main__":
    main()

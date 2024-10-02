#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <map>
#include <vector>
#include <chrono>
#include <thread>
#include <mutex>

const size_t TOPK = 10;

using Counter = std::map<std::string, std::size_t>;
std::mutex counter_mutex; 

std::string tolower(const std::string &str);

void count_words(std::istream& stream, Counter& local_counter);

void process_file(const std::string& filename, Counter& global_counter);

void print_topk(std::ostream& stream, const Counter&, const size_t k);

int main(int argc, char *argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: topk_words [FILES...]\n";
        return EXIT_FAILURE;
    }

    auto start = std::chrono::high_resolution_clock::now();
    Counter freq_dict;
    std::vector<std::thread> threads;

    for (int i = 1; i < argc; ++i) {
        threads.emplace_back(process_file, std::string(argv[i]), std::ref(freq_dict));
    }

    for (auto& t : threads) {
        t.join();
    }

    print_topk(std::cout, freq_dict, TOPK);
    auto end = std::chrono::high_resolution_clock::now();
    auto elapsed_ms = std::chrono::duration_cast<std::chrono::microseconds>(end - start);
    std::cout << "Elapsed time is " << elapsed_ms.count() << " us\n";

    return EXIT_SUCCESS;
}

std::string tolower(const std::string &str) 
    {
        std::string lower_str;
        std::transform(std::cbegin(str), std::cend(str),
            std::back_inserter(lower_str),
            [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
        return lower_str;
    };



void count_words(std::istream& stream, Counter& local_counter) {
    std::for_each(std::istream_iterator<std::string>(stream),
                  std::istream_iterator<std::string>(),
                  [&local_counter](const std::string &s) { ++local_counter[tolower(s)]; });
}

void process_file(const std::string& filename, Counter& global_counter) {
    std::ifstream input{filename};
    if (!input.is_open()) {
        std::cerr << "Failed to open file " << filename << '\n';
        return;
    }

    Counter local_counter;
    count_words(input, local_counter);

    std::lock_guard<std::mutex> lock(counter_mutex);
    for (const auto& [word, count] : local_counter) {
        global_counter[word] += count;
    }
}

void print_topk(std::ostream& stream, const Counter& counter, const size_t k) {
    std::vector<Counter::const_iterator> words;
    words.reserve(counter.size());
    for (auto it = std::cbegin(counter); it != std::cend(counter); ++it) {
        words.push_back(it);
    }

    std::partial_sort(
        std::begin(words), std::begin(words) + k, std::end(words),
        [](auto lhs, auto &rhs) { return lhs->second > rhs->second; });

    std::for_each(
        std::begin(words), std::begin(words) + k,
        [&stream](const Counter::const_iterator &pair) {
            stream << std::setw(4) << pair->second << " " << pair->first
                      << '\n';
        });
}
